"""
AI Research Assistant — Flask Backend
Serves the professional web UI and exposes REST APIs for all AI features.
"""

import os
import secrets
from flask import Flask, render_template, request, jsonify, session
from research_assistant import (
    search_all_sources,
    extract_pdf_text_chunked,
    answer_with_rag,
    generate_paper_report,
    answer_question_about_selected_paper,
    generate_advanced_code,
    generate_pdf_summary_report,
    compare_two_papers_rag,
    analyze_topic_multi_paper,
)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", secrets.token_hex(32))
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32 MB

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

@app.route("/")
def index():
    return render_template("index.html")


# ──────────────────────────────────────────────────────────────
# API — SEARCH PAPERS
# ──────────────────────────────────────────────────────────────

@app.route("/api/search", methods=["POST"])
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

@app.route("/api/paper-report", methods=["POST"])
def api_paper_report():
    paper = request.get_json(silent=True) or {}
    report = generate_paper_report(paper)
    return jsonify({"report": report})


# ──────────────────────────────────────────────────────────────
# API — PAPER Q&A
# ──────────────────────────────────────────────────────────────

@app.route("/api/paper-question", methods=["POST"])
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

@app.route("/api/pdf-upload", methods=["POST"])
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

@app.route("/api/pdf-question", methods=["POST"])
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

@app.route("/api/pdf-summary", methods=["POST"])
def api_pdf_summary():
    sid = _sid()
    if sid not in _pdf_store:
        return jsonify({"error": "No PDF loaded. Please upload a PDF first."}), 400
    summary = generate_pdf_summary_report(_pdf_store[sid]["full_text"])
    return jsonify({"summary": summary})


# ──────────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────
# API — CODE GENERATOR
# ──────────────────────────────────────────────────────────────

@app.route("/api/generate-code", methods=["POST"])
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

@app.route("/api/compare-papers", methods=["POST"])
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


@app.route("/api/compare-top-papers", methods=["POST"])
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


# ──────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000)
