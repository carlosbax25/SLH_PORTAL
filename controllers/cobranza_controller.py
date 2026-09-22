"""Controlador para el módulo Cobranza - Pre Jurídica."""
import json
from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from services.sheets_service import get_prejuridica_clients
from services.cobranza_service import (
    load_cobranza_tracking, save_notification, can_send_notif2, days_until_notif2,
    _send_cobro_email, validate_email,
)
from services.fiorentti_service import get_fiorentti_clients, _send_fiorentti_aviso, _build_fiorentti_html
from security.middleware import SecurityMiddleware

cobranza_bp = Blueprint("cobranza", __name__, url_prefix="/cobranza")


@cobranza_bp.route("/")
def index():
    return redirect(url_for('process.detail', slug='cobranza'))


@cobranza_bp.route("/fiorentti")
def fiorentti():
    try:
        clients = get_fiorentti_clients()
    except Exception as e:
        clients = []
    clients.sort(key=lambda c: c["mora"] or 0, reverse=True)
    total = len(clients)
    mora_total = sum(c["mora"] for c in clients if c["mora"])
    return render_template("cobranza/fiorentti.html", clients=clients, total=total, mora_total=mora_total)


@cobranza_bp.route("/fiorentti/preview-aviso", methods=["POST"])
def fiorentti_preview_aviso():
    """Genera el HTML del aviso para previsualización — NO envía nada."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Datos requeridos"}), 400

    propietario = SecurityMiddleware.sanitize_input(data.get("propietario", ""))
    torre       = SecurityMiddleware.sanitize_input(data.get("torre", ""))
    apto        = SecurityMiddleware.sanitize_input(data.get("apto", ""))
    mora        = data.get("mora", 0)

    subject, html = _build_fiorentti_html(propietario, torre, apto, mora)

    # El logo viene embebido como cid: en el email, en la preview lo reemplazamos
    # por la URL estática para que se vea en el iframe
    html_preview = html.replace('src="cid:logo"', 'src="/static/LOGO-SLH.png"')

    return jsonify({"subject": subject, "html": html_preview})


@cobranza_bp.route("/fiorentti/enviar-aviso", methods=["POST"])
def fiorentti_enviar_aviso():
    """Envía (o simula) el aviso pre-jurídico individual de Fiorentti."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Datos requeridos"}), 400

    propietario = SecurityMiddleware.sanitize_input(data.get("propietario", ""))
    torre       = SecurityMiddleware.sanitize_input(data.get("torre", ""))
    apto        = SecurityMiddleware.sanitize_input(data.get("apto", ""))
    email       = SecurityMiddleware.sanitize_input(data.get("email", ""))
    mora        = data.get("mora", 0)

    if not email:
        return jsonify({"error": "Este propietario no tiene correo registrado"}), 400

    result = _send_fiorentti_aviso(email, propietario, torre, apto, mora)

    from services.fiorentti_service import SEND_DISABLED, TEST_EMAIL as FTEST
    if result:
        destino = FTEST if SEND_DISABLED else email
        return jsonify({"success": True, "message": f"Aviso enviado a {destino}"})
    else:
        return jsonify({"error": "Error al enviar el correo. Revisa la configuración SMTP."}), 500

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
    correo_invalido = 0
    notif1_enviadas = 0
    notif2_enviadas = 0

    for c in clients:
        # Stable key for tracking (doesn't change when Sheet rows shift)
        stable_key = f"{c['cedula']}_{c['conjunto']}" if c['cedula'] else f"{c['propietario']}_{c['conjunto']}"
        c["stable_key"] = stable_key
        info = tracking.get(stable_key, {})
        c["notif1_date"] = info.get("notif1_date", "")[:16].replace("T", " ") if info.get("notif1_date") else ""
        c["notif2_date"] = info.get("notif2_date", "")[:16].replace("T", " ") if info.get("notif2_date") else ""
        c["notif1_sent"] = bool(info.get("notif1_date"))
        c["notif2_sent"] = bool(info.get("notif2_date"))
        c["can_notif2"] = can_send_notif2(stable_key) if c["notif1_sent"] else False
        c["days_remaining"] = days_until_notif2(stable_key) if c["notif1_sent"] and not c["notif2_sent"] else -1
        if c["tiene_correo"]:
            check = validate_email(c["correo"])
            c["correo_valido"] = check["valid"]
            c["correo_error"] = check.get("reason", "") if not check["valid"] else ""
            if check["valid"]:
                con_correo += 1
            else:
                correo_invalido += 1
        else:
            c["correo_valido"] = False
            c["correo_error"] = ""
            sin_correo += 1
        if c["notif1_sent"]:
            notif1_enviadas += 1
        if c["notif2_sent"]:
            notif2_enviadas += 1

    metrics = {
        "total": total,
        "con_correo": con_correo,
        "sin_correo": sin_correo,
        "correo_invalido": correo_invalido,
        "notif1": notif1_enviadas,
        "notif2": notif2_enviadas,
        "pendientes": total - notif1_enviadas,
    }
    return render_template("cobranza/notificaciones.html", clients=clients, metrics=metrics)


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
    cedula = SecurityMiddleware.sanitize_input(data.get("cedula", ""))
    mora = SecurityMiddleware.sanitize_input(data.get("mora", ""))
    correo = SecurityMiddleware.sanitize_input(data.get("correo", ""))
    correo_manual = SecurityMiddleware.sanitize_input(data.get("correo_manual", ""))

    # Stable key for tracking
    stable_key = f"{cedula}_{conjunto}" if cedula else f"{propietario}_{conjunto}"

    email_to = correo_manual if correo_manual else correo
    if not email_to:
        return jsonify({"error": "No hay correo electrónico para enviar"}), 400

    # Validate email before sending
    check = validate_email(email_to)
    if not check["valid"]:
        return jsonify({"error": f"Correo inválido: {check['reason']}"}), 400

    success = _send_cobro_email(email_to, propietario, conjunto, mora, notif_num,
                               data.get("torre", ""), data.get("apto", ""))
    if success:
        save_notification(stable_key, notif_num, {
            "propietario": propietario,
            "conjunto": conjunto,
            "email": email_to,
        })
        return jsonify({"success": True, "message": f"Notificación {notif_num} enviada a {email_to}"})
    else:
        return jsonify({"error": "Error al enviar el correo"}), 500


@cobranza_bp.route("/envio-masivo", methods=["POST"])
def envio_masivo():
    """Envía Aviso 1 masivamente a todos los propietarios pendientes con correo."""
    try:
        clients = get_prejuridica_clients()
    except Exception as e:
        return jsonify({"error": f"Error obteniendo clientes: {e}"}), 500

    tracking = load_cobranza_tracking()
    enviados = 0
    errores = 0
    omitidos = 0
    detalles = []

    for c in clients:
        stable_key = f"{c['cedula']}_{c['conjunto']}" if c['cedula'] else f"{c['propietario']}_{c['conjunto']}"
        info = tracking.get(stable_key, {})

        # Skip if already sent
        if info.get("notif1_date"):
            continue

        correo = c.get("correo", "").strip()
        if not correo:
            omitidos += 1
            detalles.append({"propietario": c["propietario"], "conjunto": c["conjunto"], "status": "sin_correo"})
            continue

        # Validate email domain before sending
        check = validate_email(correo)
        if not check["valid"]:
            omitidos += 1
            detalles.append({"propietario": c["propietario"], "conjunto": c["conjunto"],
                             "status": "correo_invalido", "reason": check["reason"]})
            continue

        try:
            success = _send_cobro_email(
                correo, c["propietario"], c["conjunto"], c["mora"], 1,
                c.get("torre", ""), c.get("apto", "")
            )
            if success:
                save_notification(stable_key, 1, {
                    "propietario": c["propietario"],
                    "conjunto": c["conjunto"],
                    "email": correo,
                })
                enviados += 1
                detalles.append({"propietario": c["propietario"], "conjunto": c["conjunto"], "status": "enviado"})
            else:
                errores += 1
                detalles.append({"propietario": c["propietario"], "conjunto": c["conjunto"], "status": "error"})
        except Exception:
            errores += 1
            detalles.append({"propietario": c["propietario"], "conjunto": c["conjunto"], "status": "error"})

    return jsonify({
        "success": True,
        "enviados": enviados,
        "errores": errores,
        "omitidos": omitidos,
        "detalles": detalles,
    })
