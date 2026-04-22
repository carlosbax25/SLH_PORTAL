"""Controlador para el módulo Jurídica - Demandas/Condominios."""
import os
import json
from flask import Blueprint, render_template, request, send_file, jsonify, abort
from services.sheets_service import get_juridica_clients
from services.demanda_service import (
    generate_demanda, is_demanda_generated, get_demanda_info, get_all_generated,
    GENERATED_DIR,
)
from security.middleware import SecurityMiddleware

juridica_bp = Blueprint("juridica", __name__, url_prefix="/juridica")


@juridica_bp.route("/")
def index():
    """Panel principal de Jurídica con opciones."""
    return render_template("juridica/index.html")


@juridica_bp.route("/demandas")
def demandas():
    """Vista de Demandas/Condominios - lista clientes JURIDICA."""
    try:
        clients = get_juridica_clients()
    except Exception:
        clients = []
    generated = get_all_generated()
    total_clients = len(clients)
    total_generated = 0
    total_pending = 0
    conjuntos = set()
    for c in clients:
        c["demanda_generada"] = c["cedula"] in generated
        conjuntos.add(c["conjunto"])
        info = generated.get(c["cedula"])
        if info:
            total_generated += 1
            c["demanda_fecha"] = info.get("generated_at", "")[:16].replace("T", " ")
            c["demanda_filename"] = info.get("filename", "")
            c["prev_hechos"] = json.dumps(info.get("hechos", []))
            c["prev_pretensiones"] = json.dumps(info.get("pretensiones", []))
            c["prev_medida"] = info.get("medida_cautelar", "")
        else:
            total_pending += 1
    metrics = {
        "total": total_clients,
        "generadas": total_generated,
        "pendientes": total_pending,
        "conjuntos": len(conjuntos),
    }
    return render_template("juridica/demandas.html", clients=clients, metrics=metrics)


@juridica_bp.route("/generar-demanda", methods=["POST"])
def generar_demanda():
    """Genera documento de demanda para un cliente."""
    data = request.get_json()
    if not data or "cedula" not in data:
        return jsonify({"error": "Cédula requerida"}), 400

    cedula = SecurityMiddleware.sanitize_input(data["cedula"])
    propietario = SecurityMiddleware.sanitize_input(data.get("propietario", ""))
    conjunto = SecurityMiddleware.sanitize_input(data.get("conjunto", ""))
    torre = SecurityMiddleware.sanitize_input(data.get("torre", ""))
    apto = SecurityMiddleware.sanitize_input(data.get("apto", ""))
    mora = SecurityMiddleware.sanitize_input(data.get("mora", ""))
    correo = SecurityMiddleware.sanitize_input(data.get("correo", ""))

    obligation_data = data.get("obligaciones")
    if obligation_data:
        obligation_data = [
            {
                "concepto": SecurityMiddleware.sanitize_input(o.get("concepto", "")),
                "valor": SecurityMiddleware.sanitize_input(o.get("valor", "$0")),
            }
            for o in obligation_data
        ]

    pretensiones_data = data.get("pretensiones")
    if pretensiones_data:
        pretensiones_data = [
            {
                "concepto": SecurityMiddleware.sanitize_input(o.get("concepto", "")),
                "valor": SecurityMiddleware.sanitize_input(o.get("valor", "$0")),
            }
            for o in pretensiones_data
        ]

    medida_cautelar_data = data.get("medida_cautelar", "")
    if medida_cautelar_data:
        medida_cautelar_data = SecurityMiddleware.sanitize_input(medida_cautelar_data)

    client = {
        "cedula": cedula,
        "propietario": propietario,
        "conjunto": conjunto,
        "torre": torre,
        "apto": apto,
        "mora": mora,
        "correo": correo,
    }

    try:
        filepath = generate_demanda(client, obligation_data, pretensiones_data,
                                    medida_cautelar_text=medida_cautelar_data)
        filename = os.path.basename(filepath)
        return send_file(filepath, as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@juridica_bp.route("/descargar/<filename>")
def descargar(filename: str):
    """Descarga un documento de demanda generado."""
    safe = SecurityMiddleware.sanitize_input(filename)
    filepath = os.path.join(GENERATED_DIR, safe)
    if not os.path.exists(filepath):
        abort(404)
    return send_file(filepath, as_attachment=True, download_name=safe)


@juridica_bp.route("/preview/<filename>")
def preview(filename: str):
    """Vista previa de un documento de demanda."""
    safe = SecurityMiddleware.sanitize_input(filename)
    filepath = os.path.join(GENERATED_DIR, safe)
    if not os.path.exists(filepath):
        abort(404)
    return render_template("juridica/preview.html", filename=safe)
