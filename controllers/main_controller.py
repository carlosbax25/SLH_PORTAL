"""Controlador principal del dashboard."""
from flask import Blueprint, render_template, redirect, url_for
from models.process_model import get_all_processes

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
@main_bp.route('/dashboard')
def dashboard():
    """Renderiza el dashboard con todas las tarjetas de procesos."""
    processes = get_all_processes()
    return render_template('dashboard.html', processes=processes)
