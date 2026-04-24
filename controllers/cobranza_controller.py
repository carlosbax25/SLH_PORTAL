"""Controlador para el módulo Cobranza - Pre Jurídica."""
import json
from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from services.sheets_service import get_prejuridica_clients
from services.cobranza_service import (
    load_cobranza_tracking, save_notification, can_send_notif2, days_until_notif2,
    _send_cobro_email, TEST_EMAIL,
)
from security.middleware import SecurityMiddleware

cobranza_bp = Blueprint("cobranza", __name__, url_prefix="/cobranza")


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

    success = _send_cobro_email(email_to, propietario, conjunto, mora, notif_num,
                               data.get("torre", ""), data.get("apto", ""))
    if success:
        save_notification(stable_key, notif_num, {
            "propietario": propietario,
            "conjunto": conjunto,
            "email": email_to,
        })
        return jsonify({"success": True, "message": f"Notificación {notif_num} enviada (modo prueba: {TEST_EMAIL})"})
    else:
        return jsonify({"error": "Error al enviar el correo"}), 500
