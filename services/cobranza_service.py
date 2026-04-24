"""Servicio de tracking para notificaciones de cobranza PRE JURIDICA."""
import json
import os
import re
import smtplib
import time
import urllib.parse
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from services.sheets_tracking import _api_request

COL_TZ = timezone(timedelta(hours=-5))
COBRANZA_SHEET = "COBRANZA_TRACKING"

TEST_EMAIL = "carlosbax25@gmail.com"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")

# Cache
_cobranza_cache = {"data": None, "time": 0}
_COBRANZA_CACHE_TTL = 120  # 2 minutes

_cobranza_cache = {"data": None, "time": 0}
CACHE_TTL = 120  # 2 minutes


def _ensure_cobranza_sheet():
    result = _api_request("GET", "?fields=sheets.properties.title")
    if not result:
        return
    sheets = [s["properties"]["title"] for s in result.get("sheets", [])]
    if COBRANZA_SHEET in sheets:
        return
    _api_request("POST", ":batchUpdate", {
        "requests": [{"addSheet": {"properties": {"title": COBRANZA_SHEET}}}]
    })
    rng = urllib.parse.quote(f"{COBRANZA_SHEET}!A1:G1")
    _api_request("PUT", f"values/{rng}?valueInputOption=RAW", {
        "values": [["ROW_ID", "PROPIETARIO", "CONJUNTO", "NOTIF1_DATE",
                     "NOTIF1_EMAIL", "NOTIF2_DATE", "NOTIF2_EMAIL"]]
    })


def load_cobranza_tracking() -> dict:
    now = time.time()
    if _cobranza_cache["data"] is not None and (now - _cobranza_cache["time"]) < _COBRANZA_CACHE_TTL:
        return _cobranza_cache["data"]
    _ensure_cobranza_sheet()
    rng = urllib.parse.quote(f"{COBRANZA_SHEET}!A2:G5000")
    result = _api_request("GET", f"values/{rng}")
    if not result:
        return {}
    tracking = {}
    for row in result.get("values", []):
        if row:
            row_id = row[0]
            row_id = re.sub(r'^R\d+_', '', row_id)
            tracking[row_id] = {
                "propietario": row[1] if len(row) > 1 else "",
                "conjunto": row[2] if len(row) > 2 else "",
                "notif1_date": row[3] if len(row) > 3 else "",
                "notif1_email": row[4] if len(row) > 4 else "",
                "notif2_date": row[5] if len(row) > 5 else "",
                "notif2_email": row[6] if len(row) > 6 else "",
            }
    _cobranza_cache["data"] = tracking
    _cobranza_cache["time"] = now
    return tracking


def save_notification(row_id: str, notif_num: int, data: dict):
    """Guarda una notificación enviada (1 o 2)."""
    _cobranza_cache["data"] = None  # Invalidate cache
    _ensure_cobranza_sheet()
    now = datetime.now(COL_TZ).isoformat()

    # Check if exists
    rng = urllib.parse.quote(f"{COBRANZA_SHEET}!A2:A5000")
    result = _api_request("GET", f"values/{rng}")
    rows = result.get("values", []) if result else []
    row_idx = None
    for i, r in enumerate(rows):
        if r and r[0] == row_id:
            row_idx = i + 2
            break

    if row_idx:
        # Update existing row
        existing = _api_request("GET",
            f"values/{urllib.parse.quote(f'{COBRANZA_SHEET}!A{row_idx}:G{row_idx}')}")
        vals = existing.get("values", [[]])[0] if existing else []
        while len(vals) < 7:
            vals.append("")
        if notif_num == 1:
            vals[3] = now
            vals[4] = data.get("email", "")
        else:
            vals[5] = now
            vals[6] = data.get("email", "")
        rng = urllib.parse.quote(f"{COBRANZA_SHEET}!A{row_idx}:G{row_idx}")
        _api_request("PUT", f"values/{rng}?valueInputOption=RAW", {"values": [vals]})
    else:
        new_row = [
            row_id, data.get("propietario", ""), data.get("conjunto", ""),
            now if notif_num == 1 else "",
            data.get("email", "") if notif_num == 1 else "",
            now if notif_num == 2 else "",
            data.get("email", "") if notif_num == 2 else "",
        ]
        rng = urllib.parse.quote(f"{COBRANZA_SHEET}!A:G")
        _api_request("POST",
            f"values/{rng}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS",
            {"values": [new_row]})


def get_notification_status(row_id: str) -> dict:
    """Retorna el estado de notificaciones para un propietario."""
    tracking = load_cobranza_tracking()
    return tracking.get(row_id, {})


def can_send_notif2(row_id: str) -> bool:
    """Verifica si han pasado 10 días calendario desde la notificación 1."""
    info = get_notification_status(row_id)
    notif1 = info.get("notif1_date", "")
    if not notif1:
        return False
    try:
        d1 = datetime.fromisoformat(notif1).date()
        today = datetime.now(COL_TZ).date()
        return (today - d1).days >= 10
    except Exception:
        return False


def days_until_notif2(row_id: str) -> int:
    """Retorna días calendario restantes. 0 = ya se puede enviar."""
    info = get_notification_status(row_id)
    notif1 = info.get("notif1_date", "")
    if not notif1:
        return -1
    try:
        d1 = datetime.fromisoformat(notif1).date()
        today = datetime.now(COL_TZ).date()
        elapsed = (today - d1).days
        remaining = 9 - elapsed
        return max(0, remaining)
    except Exception:
        return -1


def find_eligible_for_aviso2(tracking: dict, today) -> list[str]:
    """Retorna lista de stable_keys elegibles para Aviso 2 automático.
    
    Un registro es elegible si:
    - notif1_date no está vacío
    - notif2_date está vacío
    - (today - notif1_date).days >= 10
    """
    eligible = []
    for key, info in tracking.items():
        notif1 = info.get("notif1_date", "")
        notif2 = info.get("notif2_date", "")
        if not notif1 or notif2:
            continue
        try:
            d1 = datetime.fromisoformat(notif1).date()
            if (today - d1).days >= 10:
                eligible.append(key)
        except Exception:
            continue
    return eligible


def run_auto_aviso2() -> dict:
    """Detecta propietarios elegibles y envía Aviso 2 automáticamente."""
    from services.sheets_service import get_prejuridica_clients
    
    result = {"elegibles": 0, "enviados": 0, "omitidos": 0, "errores": 0}
    
    tracking = load_cobranza_tracking()
    today = datetime.now(COL_TZ).date()
    eligible_keys = find_eligible_for_aviso2(tracking, today)
    result["elegibles"] = len(eligible_keys)
    
    print(f"[Auto Aviso 2] Inicio: {len(eligible_keys)} propietarios elegibles")
    
    if not eligible_keys:
        return result
    
    # Get current client data for email details
    try:
        clients = get_prejuridica_clients()
    except Exception as e:
        print(f"[Auto Aviso 2] Error obteniendo clientes: {e}")
        result["errores"] = len(eligible_keys)
        return result
    
    # Build lookup by stable_key
    client_map = {}
    for c in clients:
        key = f"{c['cedula']}_{c['conjunto']}" if c['cedula'] else f"{c['propietario']}_{c['conjunto']}"
        client_map[key] = c
    
    for key in eligible_keys:
        try:
            client = client_map.get(key)
            if not client:
                print(f"[Auto Aviso 2] Omitido {key}: no encontrado en clientes PRE JURIDICA")
                result["omitidos"] += 1
                continue
            
            correo = client.get("correo", "").strip()
            if not correo:
                print(f"[Auto Aviso 2] Omitido {key}: sin correo electrónico")
                result["omitidos"] += 1
                continue
            
            success = _send_cobro_email(
                correo, client["propietario"], client["conjunto"],
                client["mora"], 2, client.get("torre", ""), client.get("apto", "")
            )
            
            if success:
                save_notification(key, 2, {
                    "propietario": client["propietario"],
                    "conjunto": client["conjunto"],
                    "email": correo,
                })
                print(f"[Auto Aviso 2] Enviado: {key} -> {correo}")
                result["enviados"] += 1
            else:
                print(f"[Auto Aviso 2] Error enviando a {key}")
                result["errores"] += 1
        except Exception as e:
            print(f"[Auto Aviso 2] Error procesando {key}: {e}")
            result["errores"] += 1
    
    print(f"[Auto Aviso 2] Resumen: {result['enviados']} enviados, "
          f"{result['omitidos']} omitidos, {result['errores']} errores "
          f"de {result['elegibles']} elegibles")
    
    return result


def _send_cobro_email(to_email: str, propietario: str, conjunto: str,
                       mora: str, notif_num: int, torre: str = "", apto: str = "") -> bool:
    """Envía correo de cobro pre-jurídico."""
    if not SMTP_USER or not SMTP_PASS:
        return False

    tipo = "PRIMER AVISO" if notif_num == 1 else "SEGUNDO Y ÚLTIMO AVISO"
    subject = f"SLH - {tipo} de Cobro Pre-Jurídico - {conjunto} - {propietario}"

    ubicacion = f"Conjunto Residencial {conjunto}"
    if torre:
        ubicacion += f", Torre {torre}"
    if apto:
        ubicacion += f", Apartamento {apto}"

    # Contact info by conjunto group
    grupo_b = ["IGUAZU", "IGUAZÚ", "MANATI", "MANATÍ", "MALIBU", "MALIBÚ", "CANDIL"]
    conj_upper = conjunto.upper().strip()
    if conj_upper in grupo_b:
        contacto = """
            <p>Para mayor información, puede comunicarse con nosotros a través de los
            siguientes canales de atención:</p>
            <p>📱 Línea móvil: <strong>+57 318 467 2539</strong><br>
            📞 Línea Fija: <strong>(065) 679 0670</strong><br>
            ✉️ Correo electrónico: <strong>gestorslh757@gmail.com</strong></p>
        """
    else:
        contacto = """
            <p>Para mayor información, puede comunicarse con nosotros a través de los
            siguientes canales de atención:</p>
            <p>📱 Línea móvil: <strong>+57 315 046 3711</strong><br>
            📞 Línea Fija: <strong>(065) 679 0670</strong><br>
            ✉️ Correo electrónico: <strong>gestorslh077@gmail.com</strong></p>
        """

    html = f"""
    <html><body style="font-family:Arial,sans-serif;margin:0;padding:0;background:#f5f5f5;">
    <div style="max-width:600px;margin:20px auto;background:#fff;border-radius:8px;overflow:hidden;">
        <div style="background:#1a1a2e;padding:20px;">
            <table style="width:100%;"><tr>
                <td style="text-align:left;"><img src="cid:logo" style="height:70px;" alt="SLH"></td>
                <td style="text-align:right;vertical-align:middle;">
                    <span style="color:#966e1e;font-size:18px;font-weight:bold;">{tipo}</span><br>
                    <span style="color:#a0a0b8;font-size:13px;">Cobro Pre-Jurídico</span>
                </td>
            </tr></table>
        </div>
        <div style="padding:24px;text-align:justify;">
            <p>Señor(a): <strong>{propietario}</strong></p>
            <p>Cordial saludo,</p>
            <p>A la fecha, registra una obligación en mora con el <strong>{ubicacion}</strong>,
            por concepto de expensas comunes, por valor de <strong>{mora}</strong>.</p>
"""

    if notif_num == 1:
        html += """
            <p>Se le requiere realizar el pago a la mayor brevedad, a fin de evitar el
            inicio de acciones legales. En caso de no obtener respuesta dentro de los
            <strong>diez (10) días calendario</strong> siguientes al recibo de la presente,
            se emitirá un segundo y último requerimiento previo al inicio del respectivo
            proceso ejecutivo, con inclusión de intereses, costas y agencias en derecho.</p>
        """
    else:
        html += """
            <p><strong>Este es el segundo y último requerimiento.</strong> De no recibir
            respuesta o evidencia de pago, se procederá de manera inmediata con el inicio
            del respectivo proceso ejecutivo para el cobro de la obligación, junto con los
            intereses, costas y agencias en derecho correspondientes.</p>
        """

    html += f"""
            {contacto}
            <p>Cordialmente,<br><strong>Sebastián Legal House S.A.S.</strong><br>
            Área de Administración – Conjunto Residencial {conjunto}</p>
        </div>
        <div style="background:#1a1a2e;padding:12px;text-align:center;">
            <p style="color:#a0a0b8;font-size:11px;margin:0;">
                Este es un mensaje automático del sistema de cobranza SLH.
            </p>
        </div>
    </div></body></html>
    """

    # TEST MODE: send to test email instead of real recipient
    actual_to = TEST_EMAIL

    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"] = f"Cobranza SLH <{SMTP_USER}>"
    msg["To"] = actual_to
    msg.attach(MIMEText(html, "html"))

    # Attach logo
    import os as _os
    from email.mime.image import MIMEImage
    logo_path = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                              "static", "LOGO-SLH.png")
    if _os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            img = MIMEImage(f.read())
            img.add_header("Content-ID", "<logo>")
            msg.attach(img)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, [actual_to], msg.as_string())
        return True
    except Exception as e:
        print(f"Error sending cobro email: {e}")
        return False
