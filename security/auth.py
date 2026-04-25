"""Módulo de autenticación y control de acceso por rol."""
import json
import os
import urllib.parse
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash, generate_password_hash

# --- Config ---
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_USERS_FILE = os.path.join(_BASE_DIR, "users.json")
_AUTH_SHEET = "AUTH_USERS"

# --- Default users ---
_DEFAULT_HASH = generate_password_hash("slh2026")

_DEFAULT_USERS = {
    "gerenciaslh":     {"password_hash": _DEFAULT_HASH, "modules": ["cobranza", "juridica", "inmobiliaria"]},
    "itslh":           {"password_hash": _DEFAULT_HASH, "modules": ["cobranza", "juridica", "inmobiliaria"]},
    "cobranzaslh":     {"password_hash": _DEFAULT_HASH, "modules": ["cobranza"]},
    "juridicaslh":     {"password_hash": _DEFAULT_HASH, "modules": ["juridica"]},
    "inmobiliariaslh": {"password_hash": _DEFAULT_HASH, "modules": ["inmobiliaria"]},
}


def _ensure_auth_sheet():
    """Crea la hoja AUTH_USERS si no existe."""
    from services.sheets_tracking import _api_request
    result = _api_request("GET", "?fields=sheets.properties.title")
    if not result:
        return
    sheets = [s["properties"]["title"] for s in result.get("sheets", [])]
    if _AUTH_SHEET in sheets:
        return
    _api_request("POST", ":batchUpdate", {
        "requests": [{"addSheet": {"properties": {"title": _AUTH_SHEET}}}]
    })
    rng = urllib.parse.quote(f"{_AUTH_SHEET}!A1:C1")
    _api_request("PUT", f"values/{rng}?valueInputOption=RAW", {
        "values": [["USERNAME", "PASSWORD_HASH", "MODULES"]]
    })


def _load_users_from_sheets() -> dict | None:
    """Lee usuarios desde Google Sheets. Retorna None si falla."""
    try:
        from services.sheets_tracking import _api_request
        _ensure_auth_sheet()
        rng = urllib.parse.quote(f"{_AUTH_SHEET}!A2:C20")
        result = _api_request("GET", f"values/{rng}")
        if not result or not result.get("values"):
            return None
        users = {}
        for row in result.get("values", []):
            if len(row) >= 3:
                username = row[0].strip()
                users[username] = {
                    "password_hash": row[1],
                    "modules": json.loads(row[2]),
                }
        return users if users else None
    except Exception as e:
        print(f"Error loading users from Sheets: {e}")
        return None


def _save_users_to_sheets(users: dict):
    """Guarda usuarios en Google Sheets."""
    try:
        from services.sheets_tracking import _api_request
        _ensure_auth_sheet()
        # Clear existing data
        rng = urllib.parse.quote(f"{_AUTH_SHEET}!A2:C20")
        _api_request("POST", f"values/{rng}:clear")
        # Write all users
        rows = []
        for username, data in users.items():
            rows.append([username, data["password_hash"], json.dumps(data["modules"])])
        if rows:
            rng = urllib.parse.quote(f"{_AUTH_SHEET}!A2")
            _api_request("PUT", f"values/{rng}?valueInputOption=RAW", {"values": rows})
    except Exception as e:
        print(f"Error saving users to Sheets: {e}")


def _load_users() -> dict:
    """Lee usuarios desde Sheets, con fallback a JSON local, con fallback a defaults."""
    # Try Sheets first
    users = _load_users_from_sheets()
    if users:
        return users
    # Fallback to local JSON
    if os.path.exists(_USERS_FILE):
        with open(_USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    # Initialize with defaults and save to Sheets
    _save_users(_DEFAULT_USERS)
    return _DEFAULT_USERS.copy()


def _save_users(users: dict):
    """Guarda usuarios en Sheets y en JSON local como backup."""
    _save_users_to_sheets(users)
    try:
        with open(_USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


# Load on import
USERS = _load_users()

ROUTE_MODULE_MAP = {
    "/cobranza": "cobranza",
    "/juridica": "juridica",
    "/process/cobranza": "cobranza",
    "/process/juridica": "juridica",
    "/process/inmobiliaria": "inmobiliaria",
}


# --- Funciones de autenticación ---


def authenticate_user(username: str, password: str) -> dict | None:
    """Valida credenciales contra USERS. Retorna dict del usuario o None."""
    user = USERS.get(username)
    if user and check_password_hash(user["password_hash"], password):
        return user
    return None


def get_current_user() -> str | None:
    return session.get("username")


def get_user_modules() -> list[str]:
    return session.get("modules", [])


def get_required_module(path: str) -> str | None:
    for prefix, module in ROUTE_MODULE_MAP.items():
        if path.startswith(prefix):
            return module
    return None


def change_password(username: str, old_password: str, new_password: str) -> tuple[bool, str]:
    """Cambia la contraseña de un usuario. Retorna (success, message)."""
    user = USERS.get(username)
    if not user:
        return False, "Usuario no encontrado"
    if not check_password_hash(user["password_hash"], old_password):
        return False, "Contraseña actual incorrecta"
    if len(new_password) < 4:
        return False, "La nueva contraseña debe tener al menos 4 caracteres"
    USERS[username]["password_hash"] = generate_password_hash(new_password)
    _save_users(USERS)
    return True, "Contraseña actualizada"


def reset_password(username: str) -> tuple[bool, str, str]:
    """Resetea la contraseña a una temporal. Retorna (success, message, temp_password)."""
    import secrets
    user = USERS.get(username)
    if not user:
        return False, "Usuario no encontrado", ""
    temp_pw = secrets.token_urlsafe(8)  # ~11 chars, safe for URLs
    USERS[username]["password_hash"] = generate_password_hash(temp_pw)
    _save_users(USERS)
    return True, "Contraseña reseteada", temp_pw


def _send_reset_email(username: str, temp_password: str) -> bool:
    """Envía la contraseña temporal a los administradores."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    if not smtp_user or not smtp_pass:
        return False

    recipients = ["jhoana.jaraba@slh.com.co", "carlosbax25@gmail.com"]
    subject = f"SLH - Recuperación de contraseña: {username}"
    html = f"""
    <html><body style="font-family:Arial,sans-serif;background:#f5f5f5;padding:20px;">
    <div style="max-width:500px;margin:0 auto;background:#1a1a2e;border-radius:12px;overflow:hidden;">
        <div style="background:#966e1e;padding:16px;text-align:center;">
            <h2 style="color:#fff;margin:0;">Recuperación de Contraseña</h2>
        </div>
        <div style="padding:24px;color:#e0e0e0;">
            <p>El usuario <strong>{username}</strong> solicitó recuperar su contraseña.</p>
            <div style="background:#0d0d1a;border:1px solid rgba(150,110,30,0.3);border-radius:8px;padding:16px;margin:16px 0;text-align:center;">
                <p style="color:#a0a0b8;margin:0 0 8px;">Contraseña temporal:</p>
                <p style="color:#966e1e;font-size:1.4rem;font-weight:700;margin:0;letter-spacing:2px;">{temp_password}</p>
            </div>
            <p style="color:#a0a0b8;font-size:0.85rem;">El usuario debe cambiar esta contraseña después de iniciar sesión.</p>
        </div>
    </div>
    </body></html>
    """

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = f"SLH Sistema <{smtp_user}>"
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipients, msg.as_string())
        return True
    except Exception as e:
        print(f"Error sending reset email: {e}")
        return False


# --- Decoradores ---


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not get_current_user():
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated_function


def role_required(module: str):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if module not in get_user_modules():
                flash("No tiene permisos para acceder a este módulo")
                return redirect(url_for("main.dashboard"))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# --- Blueprint ---

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if get_current_user():
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = authenticate_user(username, password)
        if user:
            session["username"] = username
            session["modules"] = user["modules"]
            return redirect(url_for("main.dashboard"))
        else:
            flash("Credenciales inválidas")
    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.route("/cambiar-password", methods=["GET", "POST"])
def cambiar_password():
    if not get_current_user():
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        old_pw = request.form.get("old_password", "")
        new_pw = request.form.get("new_password", "")
        confirm_pw = request.form.get("confirm_password", "")
        if new_pw != confirm_pw:
            flash("Las contraseñas no coinciden")
        else:
            ok, msg = change_password(get_current_user(), old_pw, new_pw)
            flash(msg)
            if ok:
                return redirect(url_for("main.dashboard"))
    return render_template("cambiar_password.html")


@auth_bp.route("/olvide-password", methods=["GET", "POST"])
def olvide_password():
    if get_current_user():
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        ok, msg, temp_pw = reset_password(username)
        if ok:
            sent = _send_reset_email(username, temp_pw)
            if sent:
                flash("Se envió una contraseña temporal al administrador. Solicítela para ingresar.")
            else:
                flash("Error al enviar el correo. Contacte al administrador.")
        else:
            # Generic message to not reveal if user exists
            flash("Si el usuario existe, se enviará una contraseña temporal al administrador.")
        return redirect(url_for("auth.login"))
    return render_template("olvide_password.html")
