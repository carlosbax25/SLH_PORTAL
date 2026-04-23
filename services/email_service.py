"""Servicio de envío de correos con resumen diario."""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from datetime import datetime, timezone, timedelta

COL_TZ = timezone(timedelta(hours=-5))
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
NOTIFY_TO = os.environ.get("NOTIFY_TO", "")

MESES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}


def _build_html(data: dict) -> str:
    now = datetime.now(COL_TZ)
    fecha = f"{now.day} de {MESES[now.month]} del {now.year}"
    fecha_short = now.strftime("%d/%m/%Y")

    nuevos_html = ""
    for c in data.get("nuevos", []):
        nuevos_html += (
            f'<tr><td>{c["propietario"]}</td><td>{c["cedula"]}</td>'
            f'<td>{c["conjunto"]}</td><td>{c["mora"]}</td></tr>'
        )
    if not nuevos_html:
        nuevos_html = '<tr><td colspan="4" style="text-align:center;color:#888;">Ninguno</td></tr>'

    salieron_html = ""
    for c in data.get("salieron", []):
        salieron_html += (
            f'<tr><td>{c["propietario"]}</td><td>{c["cedula"]}</td>'
            f'<td>{c["conjunto"]}</td><td>{c.get("nuevo_estado", "")}</td></tr>'
        )
    if not salieron_html:
        salieron_html = '<tr><td colspan="4" style="text-align:center;color:#888;">Ninguno</td></tr>'

    demandas_html = ""
    for c in data.get("demandas_hoy", []):
        demandas_html += (
            f'<tr><td>{c["propietario"]}</td><td>{c["cedula"]}</td>'
            f'<td>{c["conjunto"]}</td><td>{c["mora"]}</td></tr>'
        )
    if not demandas_html:
        demandas_html = '<tr><td colspan="4" style="text-align:center;color:#888;">Ninguna</td></tr>'

    gold = "#966e1e"
    dark = "#1a1a2e"

    html = f"""
    <html><body style="margin:0;padding:0;background:#f5f5f5;font-family:Arial,sans-serif;">
    <div style="max-width:600px;margin:20px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.1);">
        <div style="background:{dark};padding:24px;text-align:center;">
            <img src="cid:logo" style="height:50px;margin-bottom:10px;" alt="SLH">
            <h1 style="color:{gold};margin:0;font-size:20px;">RESUMEN DIARIO JURÍDICA</h1>
            <p style="color:#a0a0b8;margin:4px 0 0;font-size:14px;">{fecha}</p>
        </div>

        <div style="padding:24px;">
            <div style="background:#f8f8f8;border-radius:8px;padding:16px;margin-bottom:20px;">
                <h3 style="color:{dark};margin:0 0 12px;">📊 Estado General</h3>
                <table style="width:100%;font-size:14px;">
                    <tr><td>Total en JURÍDICA:</td><td style="text-align:right;font-weight:bold;">{data["total"]}</td></tr>
                    <tr><td>Demandas generadas (total):</td><td style="text-align:right;font-weight:bold;">{data["generadas"]}</td></tr>
                    <tr><td>Pendientes:</td><td style="text-align:right;font-weight:bold;">{data["pendientes"]}</td></tr>
                </table>
            </div>
"""

    table_style = 'width:100%;border-collapse:collapse;font-size:13px;'
    th_style = f'background:{gold};color:#fff;padding:8px;text-align:left;'
    td_style = 'padding:8px;border-bottom:1px solid #eee;'

    html += f"""
            <h3 style="color:{dark};">🆕 Nuevos en JURÍDICA ({len(data.get("nuevos", []))})</h3>
            <table style="{table_style}">
                <tr><th style="{th_style}">Propietario</th><th style="{th_style}">Cédula</th>
                <th style="{th_style}">Conjunto</th><th style="{th_style}">Mora</th></tr>
                {nuevos_html}
            </table>

            <h3 style="color:{dark};margin-top:20px;">🔴 Salieron de JURÍDICA ({len(data.get("salieron", []))})</h3>
            <table style="{table_style}">
                <tr><th style="{th_style}">Propietario</th><th style="{th_style}">Cédula</th>
                <th style="{th_style}">Conjunto</th><th style="{th_style}">Nuevo Estado</th></tr>
                {salieron_html}
            </table>

            <h3 style="color:{dark};margin-top:20px;">📄 Demandas Generadas Hoy ({len(data.get("demandas_hoy", []))})</h3>
            <table style="{table_style}">
                <tr><th style="{th_style}">Propietario</th><th style="{th_style}">Cédula</th>
                <th style="{th_style}">Conjunto</th><th style="{th_style}">Mora</th></tr>
                {demandas_html}
            </table>
        </div>

        <div style="background:{dark};padding:16px;text-align:center;">
            <p style="color:#a0a0b8;margin:0;font-size:12px;">
                SLH - Centro de Automatización<br>
                <a href="https://slh-portal.onrender.com" style="color:{gold};">slh-portal.onrender.com</a>
            </p>
        </div>
    </div>
    </body></html>
    """
    return html


def send_daily_report(data: dict) -> bool:
    """Envía el resumen diario por correo."""
    if not SMTP_USER or not SMTP_PASS or not NOTIFY_TO:
        print("Email not configured: missing SMTP_USER, SMTP_PASS or NOTIFY_TO")
        return False

    now = datetime.now(COL_TZ)
    subject = f"SLH - Resumen Diario Jurídica | {now.strftime('%d/%m/%Y')}"

    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = NOTIFY_TO

    html = _build_html(data)
    msg.attach(MIMEText(html, "html"))

    # Attach logo
    logo_path = os.path.join(BASE_DIR, "static", "LOGO-SLH.png")
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            img = MIMEImage(f.read())
            img.add_header("Content-ID", "<logo>")
            msg.attach(img)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, NOTIFY_TO.split(","), msg.as_string())
        print(f"Daily report sent to {NOTIFY_TO}")
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False
