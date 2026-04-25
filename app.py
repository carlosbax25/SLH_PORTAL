"""Punto de entrada de la aplicación Flask - Dashboard de Automatización SLH."""
import os
from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, request, redirect, url_for, session, flash
from controllers.main_controller import main_bp
from controllers.process_controller import process_bp
from controllers.juridica_controller import juridica_bp
from controllers.cobranza_controller import cobranza_bp
from security.middleware import SecurityMiddleware
from security.auth import auth_bp, ROUTE_MODULE_MAP


def create_app(config_name: str = 'development') -> Flask:
    """Crea y configura la instancia de Flask."""
    app = Flask(__name__, static_folder='static', template_folder='templates')

    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(32))
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    # Registrar middleware de seguridad
    SecurityMiddleware.init_app(app)

    # Registrar Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(process_bp)
    app.register_blueprint(juridica_bp)
    app.register_blueprint(cobranza_bp)

    # Protección global de rutas
    @app.before_request
    def check_auth():
        path = request.path
        if path.startswith("/login") or path.startswith("/logout") or path.startswith("/static"):
            return None
        if not session.get("username"):
            return redirect(url_for("auth.login"))
        for prefix, module in ROUTE_MODULE_MAP.items():
            if path.startswith(prefix):
                if module not in session.get("modules", []):
                    flash("No tiene permisos para acceder a este módulo")
                    return redirect(url_for("main.dashboard"))
                break
        return None

    # Manejadores de error
    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(429)
    def rate_limited(e):
        return render_template('errors/429.html'), 429

    @app.errorhandler(500)
    def server_error(e):
        return render_template('errors/500.html'), 500

    return app


application = create_app()

# Schedule daily report at 7am Colombia time
import threading
import time
from datetime import datetime, timezone, timedelta

def _daily_scheduler():
    COL_TZ = timezone(timedelta(hours=-5))
    while True:
        now = datetime.now(COL_TZ)
        # Next 7am
        target = now.replace(hour=7, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        wait = (target - now).total_seconds()
        print(f"Next daily report in {wait/3600:.1f} hours")
        time.sleep(wait)
        try:
            from services.daily_job import run_daily_report
            run_daily_report()
        except Exception as e:
            print(f"Daily report error: {e}")

if os.environ.get("RENDER") or not os.environ.get("WERKZEUG_RUN_MAIN"):
    t = threading.Thread(target=_daily_scheduler, daemon=True)
    t.start()

if __name__ == '__main__':
    application.run(host='0.0.0.0', port=5000, debug=True)
