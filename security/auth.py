"""Módulo de autenticación y control de acceso por rol."""
import json
import os
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash, generate_password_hash

# --- Paths ---
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_USERS_FILE = os.path.join(_BASE_DIR, "users.json")

# --- Default users (used to create users.json if it doesn't exist) ---
_DEFAULT_HASH = generate_password_hash("slh2026")

_DEFAULT_USERS = {
    "gerenciaslh":     {"password_hash": _DEFAULT_HASH, "modules": ["cobranza", "juridica", "inmobiliaria"]},
    "itslh":           {"password_hash": _DEFAULT_HASH, "modules": ["cobranza", "juridica", "inmobiliaria"]},
    "cobranzaslh":     {"password_hash": _DEFAULT_HASH, "modules": ["cobranza"]},
    "juridicaslh":     {"password_hash": _DEFAULT_HASH, "modules": ["juridica"]},
    "inmobiliariaslh": {"password_hash": _DEFAULT_HASH, "modules": ["inmobiliaria"]},
}


def _load_users() -> dict:
    """Lee usuarios desde users.json. Si no existe, lo crea con defaults."""
    if os.path.exists(_USERS_FILE):
        with open(_USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    _save_users(_DEFAULT_USERS)
    return _DEFAULT_USERS.copy()


def _save_users(users: dict):
    """Guarda usuarios en users.json."""
    with open(_USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)


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
