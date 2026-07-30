"""
app/__init__.py
───────────────
Flask application factory.
"""

import os
import secrets

from flask import Flask


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )
    app.secret_key = os.environ.get("FLASK_SECRET", secrets.token_hex(32))
    app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32 MB

    # Register blueprints
    from app.routes.api import bp as api_bp
    app.register_blueprint(api_bp)

    return app
