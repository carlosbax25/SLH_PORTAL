"""Middleware de seguridad para la aplicación Flask."""
from flask import Flask


class SecurityMiddleware:
    """Aplica cabeceras y políticas de seguridad."""

    @staticmethod
    def init_app(app: Flask) -> None:
        """Registra el middleware after_request."""
        @app.after_request
        def apply_headers(response):
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['X-Frame-Options'] = 'DENY'
            response.headers['X-XSS-Protection'] = '1; mode=block'
            response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
            response.headers['Permissions-Policy'] = 'geolocation=(), camera=()'
            csp = (
                "default-src 'self'; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
                "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
                "img-src 'self' data:; "
                "script-src 'self' 'unsafe-inline'"
            )
            response.headers['Content-Security-Policy'] = csp
            return response

    @staticmethod
    def sanitize_input(value: str) -> str:
        """Sanitiza entrada del usuario contra XSS."""
        if not isinstance(value, str):
            return ''
        value = value.replace('&', '&amp;')
        value = value.replace('<', '&lt;')
        value = value.replace('>', '&gt;')
        value = value.replace('"', '&quot;')
        value = value.replace("'", '&#x27;')
        value = ''.join(ch for ch in value if ord(ch) >= 32 or ch in '\n\r\t')
        return value.strip()
