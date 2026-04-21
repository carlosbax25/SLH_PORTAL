"""Controlador de detalle de procesos."""
from flask import Blueprint, render_template, abort, jsonify
from models.process_model import get_process_by_slug
from security.middleware import SecurityMiddleware

process_bp = Blueprint('process', __name__, url_prefix='/process')


@process_bp.route('/<slug>')
def detail(slug: str):
    """Muestra el detalle de un proceso específico."""
    safe_slug = SecurityMiddleware.sanitize_input(slug)
    process = get_process_by_slug(safe_slug)
    if not process:
        abort(404)
    return render_template('process_detail.html', process=process)


@process_bp.route('/<slug>/status')
def status(slug: str):
    """API endpoint para estado del proceso."""
    safe_slug = SecurityMiddleware.sanitize_input(slug)
    process = get_process_by_slug(safe_slug)
    if not process:
        return jsonify({"error": "Proceso no encontrado"}), 404
    return jsonify({
        "name": process.name,
        "status": process.status.value,
        "success_rate": process.success_rate,
        "last_execution": str(process.last_execution),
    })
