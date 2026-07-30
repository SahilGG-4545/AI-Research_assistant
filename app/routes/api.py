"""
app/routes/api.py
──────────────────
All Flask page and API routes for the AI Research Assistant.

Endpoints:
  GET  /                        → index page
  POST /api/search              → paper search
  POST /api/paper-report        → generate paper report
  POST /api/paper-question      → Q&A on a paper abstract
  POST /api/pdf-upload          → upload & parse PDF
  POST /api/pdf-question        → RAG Q&A on uploaded PDF
  POST /api/pdf-summary         → summarise uploaded PDF
  POST /api/generate-code       → multi-agent code generation
  POST /api/compare-papers      → compare two papers
  POST /api/compare-top-papers  → multi-paper topic analysis
"""

import secrets

from flask import Blueprint, render_template, request, jsonify, session

from app.services.search import search_all_sources
from app.services.rag import extract_pdf_text_chunked, answer_with_rag
from app.services.report import generate_paper_report, generate_pdf_summary_report
from app.services.code_gen import generate_advanced_code
from app.services.analysis import (
    answer_question_about_selected_paper,
    compare_two_papers_rag,
    analyze_topic_multi_paper,
)

bp = Blueprint("api", __name__)

# Server-side PDF storage keyed by session ID
_pdf_store: dict = {}

ALLOWED_LANGUAGES = {"python", "cpp", "java", "javascript", "typescript"}


def _sid() -> str:
    """Get or create a session ID."""
    if "sid" not in session:
        session["sid"] = secrets.token_hex(16)
    return session["sid"]


# ──────────────────────────────────────────────────────────────
# PAGES
# ──────────────────────────────────────────────────────────────

@bp.route("/")
def index():
    return render_template("index.html")


# ──────────────────────────────────────────────────────────────
# API — SEARCH PAPERS
# ──────────────────────────────────────────────────────────────

@bp.route("/api/search", methods=["POST"])
def api_search():
    data = request.get_json(silent=True) or {}
    topic = str(data.get("topic", "")).strip()
    if not topic:
        return jsonify({"error": "Topic is required"}), 400
    papers = search_all_sources(topic)
    return jsonify({"papers": papers})


# ──────────────────────────────────────────────────────────────
# API — PAPER REPORT
# ──────────────────────────────────────────────────────────────

@bp.route("/api/paper-report", methods=["POST"])
def api_paper_report():
    paper = request.get_json(silent=True) or {}
    report = generate_paper_report(paper)
    return jsonify({"report": report})


# ──────────────────────────────────────────────────────────────
# API — PAPER Q&A
# ──────────────────────────────────────────────────────────────

@bp.route("/api/paper-question", methods=["POST"])
def api_paper_question():
    data = request.get_json(silent=True) or {}
    paper = data.get("paper", {})
    question = str(data.get("question", "")).strip()
    history = data.get("history", [])
    if not question:
        return jsonify({"error": "Question is required"}), 400
    answer = answer_question_about_selected_paper(paper, question, history=history)
    return jsonify({"answer": answer})


# ──────────────────────────────────────────────────────────────
# API — PDF UPLOAD
# ──────────────────────────────────────────────────────────────

@bp.route("/api/pdf-upload", methods=["POST"])
def api_pdf_upload():
    if "pdf" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files["pdf"]
    if not f.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are allowed"}), 400
    sid = _sid()
    pdf_data = extract_pdf_text_chunked(f)
    _pdf_store[sid] = {
        "full_text": pdf_data["full_text"],
        "chunks": list(pdf_data["chunks"]),
    }
    return jsonify({"success": True, "chunks": len(pdf_data["chunks"])})


# ──────────────────────────────────────────────────────────────
# API — PDF Q&A
# ──────────────────────────────────────────────────────────────

@bp.route("/api/pdf-question", methods=["POST"])
def api_pdf_question():
    sid = _sid()
    if sid not in _pdf_store:
        return jsonify({"error": "No PDF loaded. Please upload a PDF first."}), 400
    data = request.get_json(silent=True) or {}
    question = str(data.get("question", "")).strip()
    if not question:
        return jsonify({"error": "Question is required"}), 400
    result = answer_with_rag(_pdf_store[sid]["chunks"], question, with_trace=True)

    if isinstance(result, dict):
        answer = str(result.get("answer", ""))
        trace = result.get("trace", {})
    else:
        answer = str(result)
        trace = {}

    return jsonify({"answer": answer, "trace": trace})


# ──────────────────────────────────────────────────────────────
# API — PDF SUMMARY
# ──────────────────────────────────────────────────────────────

@bp.route("/api/pdf-summary", methods=["POST"])
def api_pdf_summary():
    sid = _sid()
    if sid not in _pdf_store:
        return jsonify({"error": "No PDF loaded. Please upload a PDF first."}), 400
    summary = generate_pdf_summary_report(_pdf_store[sid]["full_text"])
    return jsonify({"summary": summary})


# ──────────────────────────────────────────────────────────────
# API — CODE GENERATOR
# ──────────────────────────────────────────────────────────────

@bp.route("/api/generate-code", methods=["POST"])
def api_generate_code():
    data = request.get_json(silent=True) or {}
    task = str(data.get("task", "")).strip()
    language = str(data.get("language", "python"))
    if language not in ALLOWED_LANGUAGES:
        language = "python"
    if not task:
        return jsonify({"error": "Task description is required"}), 400

    result = generate_advanced_code(task, language=language)
    if isinstance(result, dict) and "code" in result:
        return jsonify({"code": result["code"], "trace": result.get("trace", {})})

    return jsonify({"code": result})


# ──────────────────────────────────────────────────────────────
# API — COMPARE PAPERS
# ──────────────────────────────────────────────────────────────

@bp.route("/api/compare-papers", methods=["POST"])
def api_compare_papers():
    data = request.get_json(silent=True) or {}
    paper1 = data.get("paper1", {})
    paper2 = data.get("paper2", {})
    aspect = str(data.get("aspect", "overall quality"))
    text1 = str(paper1.get("abstract", ""))
    text2 = str(paper2.get("abstract", ""))
    if not text1 or not text2:
        return jsonify({"error": "Both papers must have abstracts for comparison"}), 400
    result = compare_two_papers_rag(text1, text2, aspect)
    return jsonify({"result": result})


@bp.route("/api/compare-top-papers", methods=["POST"])
def api_compare_top_papers():
    data = request.get_json(silent=True) or {}
    topic = str(data.get("topic", "")).strip()
    aspect = str(data.get("aspect", "overall quality")).strip() or "overall quality"

    try:
        top_k = int(data.get("top_k", 3))
    except Exception:
        top_k = 3

    if not topic:
        return jsonify({"error": "Topic is required"}), 400

    result = analyze_topic_multi_paper(topic=topic, top_k=top_k, aspect=aspect)

    if isinstance(result, dict) and result.get("error"):
        return jsonify({"error": result["error"]}), 400

    return jsonify(result)
