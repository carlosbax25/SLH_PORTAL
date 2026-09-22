"""Servicio para leer y parsear la cartera del conjunto Fiorentti desde Excel."""
import os
import re
import openpyxl

EXCEL_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "CARTERA_21_SEP.xlsx")
SHEET_NAME = "Propietarios"


def _parse_cliente(cliente: str) -> tuple[str, str, str]:
    """Parsea la celda Cliente con formato 'T1-1003  JORGE VEGA'.

    Retorna (torre, apartamento, propietario).
    Ejemplos:
        'T1-1003  JORGE VEGA'  → ('T1', '1003', 'JORGE VEGA')
        'T2-205 ANA LUCIA'     → ('T2', '205',  'ANA LUCIA')
    """
    if not cliente:
        return ("", "", "")

    cliente = str(cliente).strip()

    def _clean_propietario(nombre: str) -> str:
        """Si hay '/' toma solo la parte después del slash."""
        if '/' in nombre:
            nombre = nombre.split('/', 1)[1]
        nombre = nombre.strip()
        # Overrides manuales: nombre en Excel → nombre correcto
        _overrides = {
            "BANCO DAVIVIENDA SA": "MALKA CASTRO",
        }
        return _overrides.get(nombre, nombre)

    # Intenta patrón TN-XXXX NOMBRE (torre con guion)
    match = re.match(r'^(T\d+)-(\d+)\s+(.*)', cliente, re.IGNORECASE)
    if match:
        return (match.group(1).upper(), match.group(2), _clean_propietario(match.group(3)))

    # Fallback: sin guion, p.ej. 'T1 1003 NOMBRE'
    match = re.match(r'^(T\d+)\s+(\d+)\s+(.*)', cliente, re.IGNORECASE)
    if match:
        return (match.group(1).upper(), match.group(2), _clean_propietario(match.group(3)))

    # No pudo parsear — devuelve todo como propietario
    return ("", "", _clean_propietario(cliente))


def get_fiorentti_clients() -> list[dict]:
    """Lee la hoja Propietarios del Excel y retorna lista de dicts listos para la vista."""
    wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True, data_only=True)
    ws = wb[SHEET_NAME]

    clients = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        # Saltar filas completamente vacías
        if not any(row):
            continue

        cliente_raw, identificacion, correo, telefono, mora = (
            row[0], row[1], row[2], row[3], row[4]
        )

        if not cliente_raw:
            continue

        torre, apto, propietario = _parse_cliente(cliente_raw)

        clients.append({
            "torre": torre,
            "apto": apto,
            "propietario": propietario,
            "identificacion": re.sub(r'[^0-9]', '', str(identificacion)) if identificacion else "",
            "email": str(correo).strip().lower() if correo else "",
            "telefono": str(int(telefono)) if isinstance(telefono, float) else (str(telefono).strip() if telefono else ""),
            "mora": mora if mora is not None else 0,
        })

    wb.close()
    return clients


# ---------------------------------------------------------------------------
# Envío de aviso pre-jurídico
# ---------------------------------------------------------------------------
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")

# True  → envía SIEMPRE a TEST_EMAIL (prueba de formato) — NO CAMBIAR hasta confirmar envío real
# False → envía al destinatario real del propietario
SEND_DISABLED = True
TEST_EMAIL = "carlosbax25@gmail.com"

CONJUNTO = "Fiorentti"


def _build_fiorentti_html(propietario: str, torre: str, apto: str, mora_valor) -> tuple[str, str]:
    """Genera el HTML del aviso y el asunto. Retorna (subject, html)."""
    mora_num   = float(mora_valor) if mora_valor else 0
    honorarios = mora_num * 0.10
    total      = mora_num + honorarios
    mora_fmt   = f"${mora_num:,.0f}".replace(",", ".")
    hon_fmt    = f"${honorarios:,.0f}".replace(",", ".")
    total_fmt  = f"${total:,.0f}".replace(",", ".")

    if propietario:
        saludo_nombre = f"<strong>{propietario}</strong>"
    else:
        partes = []
        if torre: partes.append(f"Torre {torre}")
        if apto:  partes.append(f"Apartamento {apto}")
        saludo_nombre = f"<strong>Propietario de inmueble {' '.join(partes)}</strong>"

    nombre_asunto = propietario or f"Torre {torre} Apto {apto}"
    subject = f"SLH - AVISO PRE-JURÍDICO - {CONJUNTO} - {nombre_asunto}"

    html = f"""
    <html><body style="font-family:Arial,sans-serif;margin:0;padding:0;background:#f5f5f5;">
    <div style="max-width:600px;margin:20px auto;background:#fff;border-radius:8px;
                overflow:hidden;box-shadow:0 4px 16px rgba(0,0,0,0.12);">
        <div style="background:#1a1a2e;padding:20px 24px;">
            <table style="width:100%;border-collapse:collapse;"><tr>
                <td style="text-align:left;vertical-align:middle;">
                    <img src="cid:logo" style="height:65px;" alt="SLH">
                </td>
                <td style="text-align:right;vertical-align:middle;">
                    <span style="color:#966e1e;font-size:17px;font-weight:bold;letter-spacing:0.5px;">
                        AVISO PRE-JURÍDICO
                    </span><br>
                    <span style="color:#a0a0b8;font-size:12px;">Cobro de Cartera – {CONJUNTO}</span>
                </td>
            </tr></table>
        </div>
        <div style="padding:28px 32px;color:#222;line-height:1.75;text-align:justify;font-size:14px;">
            <p style="margin:0 0 4px;">Señor(a): {saludo_nombre}</p>
            <p style="margin:0 0 18px;">Cordial saludo,</p>
            <p style="margin:0 0 14px;">
                Le informamos que su cartera ha sido trasladada por la administración
                <strong>Angelus PH</strong> a nuestra Casa de cobranza.
            </p>
            <p style="margin:0 0 14px;">
                A la fecha, registra una obligación en mora con el
                <strong>Conjunto Residencial {CONJUNTO}, Torre {torre},
                Apartamento {apto}</strong>, por concepto de expensas comunes,
                por valor de <strong>{mora_fmt}</strong>, más el <strong>10%</strong>
                por concepto de honorarios a esta casa de cobranza
                (<strong>{hon_fmt}</strong>), para un total de
                <strong>{total_fmt}</strong>.
            </p>
            <p style="margin:0 0 14px;">
                Se le requiere realizar el pago a la mayor brevedad, a fin de evitar
                el inicio de acciones legales. En caso de no obtener respuesta dentro
                de los <strong>cinco (5) días calendario</strong> siguientes al recibo
                de la presente, se dará inicio del respectivo proceso ejecutivo, con
                inclusión de intereses, costas y agencias en derecho.
            </p>
            <p style="margin:0 0 8px;">
                Para mayor información, puede comunicarse con nosotros a través de los
                siguientes canales de atención:
            </p>
            <table style="border-collapse:collapse;margin-bottom:20px;">
                <tr>
                    <td style="padding:3px 10px 3px 0;font-size:15px;">📱</td>
                    <td style="padding:3px 0;">Línea móvil: <strong>+57 318 467 2539</strong></td>
                </tr>
                <tr>
                    <td style="padding:3px 10px 3px 0;font-size:15px;">📞</td>
                    <td style="padding:3px 0;">Línea Fija: <strong>(065) 679 0670</strong></td>
                </tr>
                <tr>
                    <td style="padding:3px 10px 3px 0;font-size:15px;">✉️</td>
                    <td style="padding:3px 0;">
                        Correo electrónico:
                        <a href="mailto:gestorslh757@gmail.com" style="color:#966e1e;">
                            <strong>gestorslh757@gmail.com</strong>
                        </a>,
                        <a href="mailto:cobranzas@slh.com.co" style="color:#966e1e;">
                            <strong>cobranzas@slh.com.co</strong>
                        </a>
                    </td>
                </tr>
                <tr>
                    <td style="padding:3px 10px 3px 0;font-size:15px;">📍</td>
                    <td style="padding:3px 0;">
                        Ubicación: Cartagena, centro de la ciudad, sector la matuna
                        edificio comodoro piso 3 oficina 307.
                    </td>
                </tr>
            </table>
            <p style="margin:0;">
                Cordialmente,<br>
                <strong>Sebastián Legal House S.A.S.</strong><br>
                Área de Administración – Conjunto Residencial FIORENTTI
            </p>
        </div>
        <div style="background:#1a1a2e;padding:12px 24px;text-align:center;">
            <p style="color:#a0a0b8;font-size:11px;margin:0;">
                Este es un mensaje automático del sistema de cobranza SLH.
            </p>
        </div>
    </div></body></html>
    """
    return subject, html


def _send_fiorentti_aviso(to_email: str, propietario: str, torre: str,
                           apto: str, mora_valor) -> bool:
    """Envía el aviso pre-jurídico de Fiorentti.

    SEND_DISABLED=True  → destino SIEMPRE TEST_EMAIL (revisión de formato).
    SEND_DISABLED=False → destino real del propietario.
    """
    if not SMTP_USER or not SMTP_PASS:
        print("[Fiorentti] SMTP no configurado — correo no enviado.")
        return False

    subject, html = _build_fiorentti_html(propietario, torre, apto, mora_valor)
    nombre_asunto = propietario or f"Torre {torre} Apto {apto}"

    # ── Destino ───────────────────────────────────────────────────────────
    # SEND_DISABLED=True  → SIEMPRE va a TEST_EMAIL sin excepción
    # SEND_DISABLED=False → va al destinatario real
    if SEND_DISABLED:
        actual_to = TEST_EMAIL
    else:
        actual_to = to_email

    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"] = f"Cobranza SLH <{SMTP_USER}>"
    msg["To"] = actual_to
    msg.attach(MIMEText(html, "html"))

    logo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "static", "LOGO-SLH.png")
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            img = MIMEImage(f.read())
            img.add_header("Content-ID", "<logo>")
            msg.attach(img)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, [actual_to], msg.as_string())
        print(f"[Fiorentti] Email enviado a {actual_to} para {nombre_asunto}")
        return True
    except Exception as e:
        print(f"[Fiorentti] Error SMTP: {e}")
        return False
