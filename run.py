"""
run.py
──────
Application entry point.

Usage:
    python run.py              # development server on port 5000
    flask run                  # also works via standard Flask discovery
"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
