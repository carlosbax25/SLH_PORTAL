"""Controlador para el módulo Cobranza - Pre Jurídica."""
import os
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from services.sheets_service import get_prejuridica_clients
from services.cobranza_service import (
    load_cobranza_tracking, save_notification, can_send_notif2, days_until_notif2,
)
from security.middleware import SecurityMiddleware

cobranza_bp = Blueprint("cobranza", __name__, url_prefix="/cobranza")

# Test mode: all emails go to this address
TEST_EMAIL = "carlosbax25@gmail.com"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")


@cobranza_bp.route("/")
def index():
    return redirect(url_for('process.detail', slug='cobranza'))


@cobranza_bp.route("/notificaciones")
def notificaciones():
    try:
        clients = get_prejuridica_clients()
    except Exception:
        clients = []
    tracking = load_cobranza_tracking()
    total = len(clients)
    con_correo = 0
    sin_correo = 0
    notif1_enviadas = 0
    notif2_enviadas = 0

    for c in clients:
        info = tracking.get(c["row_id"], {})
        c["notif1_date"] = info.get("notif1_date", "")[:16].replace("T", " ") if info.get("notif1_date") else ""
        c["notif2_date"] = info.get("notif2_date", "")[:16].replace("T", " ") if info.get("notif2_date") else ""
        c["notif1_sent"] = bool(info.get("notif1_date"))
        c["notif2_sent"] = bool(info.get("notif2_date"))
        c["can_notif2"] = can_send_notif2(c["row_id"]) if c["notif1_sent"] else False
        c["days_remaining"] = days_until_notif2(c["row_id"]) if c["notif1_sent"] and not c["notif2_sent"] else -1
        if c["tiene_correo"]:
            con_correo += 1
        else:
            sin_correo += 1
        if c["notif1_sent"]:
            notif1_enviadas += 1
        if c["notif2_sent"]:
            notif2_enviadas += 1

    metrics = {
        "total": total,
        "con_correo": con_correo,
        "sin_correo": sin_correo,
        "notif1": notif1_enviadas,
        "notif2": notif2_enviadas,
        "pendientes": total - notif1_enviadas,
    }
    return render_template("cobranza/notificaciones.html", clients=clients, metrics=metrics)


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


@cobranza_bp.route("/enviar-notificacion", methods=["POST"])
def enviar_notificacion():
    """Envía notificación 1 o 2 a un propietario."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Datos requeridos"}), 400

    row_id = SecurityMiddleware.sanitize_input(data.get("row_id", ""))
    notif_num = data.get("notif_num", 1)
    propietario = SecurityMiddleware.sanitize_input(data.get("propietario", ""))
    conjunto = SecurityMiddleware.sanitize_input(data.get("conjunto", ""))
    mora = SecurityMiddleware.sanitize_input(data.get("mora", ""))
    correo = SecurityMiddleware.sanitize_input(data.get("correo", ""))
    correo_manual = SecurityMiddleware.sanitize_input(data.get("correo_manual", ""))

    email_to = correo_manual if correo_manual else correo
    if not email_to:
        return jsonify({"error": "No hay correo electrónico para enviar"}), 400

    success = _send_cobro_email(email_to, propietario, conjunto, mora, notif_num,
                               data.get("torre", ""), data.get("apto", ""))
    if success:
        save_notification(row_id, notif_num, {
            "propietario": propietario,
            "conjunto": conjunto,
            "email": email_to,
        })
        return jsonify({"success": True, "message": f"Notificación {notif_num} enviada (modo prueba: {TEST_EMAIL})"})
    else:
        return jsonify({"error": "Error al enviar el correo"}), 500
