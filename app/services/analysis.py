"""
app/services/analysis.py
─────────────────────────
Multi-paper topic analysis pipeline and paper comparison utilities.

Pipeline: Search Agent → Reader Agent → Compare Agent → Planner Agent
"""

import json

from core.llm import groq_chat
from app.services.search import search_all_sources
from app.utils.text import (
    _extract_json_object,
    _normalize_string_list,
    _clean_text_value,
    _markdown_cell,
)


# ──────────────────────────────────────────────────────────────
# PAPER QUESTION ANSWERING
# ──────────────────────────────────────────────────────────────

def answer_question_about_selected_paper(paper: dict, question: str, history=None):
    """Answer a question about a paper using only its abstract."""
    raw_abs = paper.get("abstract")
    abstract = (raw_abs if isinstance(raw_abs, str) else "").strip()

    if not abstract:
        return "The abstract does not contain any information to answer this question."

    title = paper.get("title", "")
    authors = ", ".join(paper.get("authors", []))

    prompt = f"""
Answer the user's question using ONLY the abstract.

Paper Title: {title}
Authors: {authors}

Abstract:
{abstract}

Question:
{question}

If the answer is not in the abstract:
Reply ONLY with:
"The abstract does not mention this information."
"""

    return groq_chat(prompt, conversation_history=history, temperature=0.2)


# ──────────────────────────────────────────────────────────────
# PAPER COMPARISON
# ──────────────────────────────────────────────────────────────

def compare_two_papers_rag(text1, text2, aspect):
    """Compare two paper abstracts across a given aspect."""
    prompt = f"""
Compare two papers based on: {aspect}

Paper 1:
{text1[:4000]}

Paper 2:
{text2[:4000]}

Write the comparison:

### Similarities
### Differences
### Strengths of Paper 1
### Strengths of Paper 2
### Final Verdict
"""

    return groq_chat(prompt, temperature=0.3)


# ──────────────────────────────────────────────────────────────
# MULTI-PAPER ANALYSIS AGENTS
# ──────────────────────────────────────────────────────────────

def search_agent_find_papers(topic: str, top_k: int = 3):
    """
    Search Agent: retrieves candidate papers and keeps top-k with usable abstracts.
    """
    try:
        top_k = int(top_k)
    except Exception:
        top_k = 3

    top_k = max(3, min(5, top_k))
    fetch_n = max(10, top_k * 4)

    candidates = search_all_sources(topic, max_results=fetch_n)

    selected = []
    for p in candidates:
        abstract = p.get("abstract")
        if not isinstance(abstract, str) or not abstract.strip():
            continue

        selected.append(
            {
                "title": _clean_text_value(p.get("title", ""), fallback="Untitled"),
                "abstract": abstract.strip(),
                "authors": p.get("authors", []) if isinstance(p.get("authors", []), list) else [],
                "year": p.get("year", ""),
                "citations": p.get("citations", 0),
                "venue": p.get("venue", ""),
                "url": p.get("url", ""),
                "source": p.get("source", "unknown"),
            }
        )

        if len(selected) >= top_k:
            break

    return selected


def reader_agent_extract_structured(paper: dict):
    """
    Reader Agent: extracts structured fields from a paper abstract.
    """
    title = _clean_text_value(paper.get("title", ""), fallback="Untitled")
    abstract = _clean_text_value(paper.get("abstract", ""), fallback="")

    prompt = f"""
You are the Reader Agent for academic paper analysis.

Extract the paper details from the abstract below.
Return ONLY a valid JSON object (no markdown, no extra text) with EXACT keys:
- problem
- method
- dataset
- results
- strengths (array of short bullet strings)
- limitations (array of short bullet strings)

If a field is missing, use "Not specified".

Title: {title}
Abstract:
{abstract[:4000]}
"""

    try:
        raw = groq_chat(prompt, temperature=0.15)
    except Exception:
        raw = "{}"

    parsed = _extract_json_object(raw)

    return {
        "title": title,
        "problem": _clean_text_value(parsed.get("problem", "Not specified")),
        "method": _clean_text_value(parsed.get("method", "Not specified")),
        "dataset": _clean_text_value(parsed.get("dataset", "Not specified")),
        "results": _clean_text_value(parsed.get("results", "Not specified")),
        "strengths": _normalize_string_list(parsed.get("strengths", [])),
        "limitations": _normalize_string_list(parsed.get("limitations", [])),
        "source": _clean_text_value(paper.get("source", "unknown"), fallback="unknown"),
        "year": _clean_text_value(paper.get("year", ""), fallback="-"),
        "url": _clean_text_value(paper.get("url", ""), fallback=""),
    }


def compare_agent_compare_structured(records, aspect="overall quality"):
    """
    Compare Agent: creates a cross-paper comparison matrix and aspect-focused verdict.
    """
    if not records:
        return "No structured records available for comparison."

    compact = []
    for r in records:
        compact.append(
            {
                "title": r.get("title", "Untitled"),
                "problem": r.get("problem", "Not specified"),
                "method": r.get("method", "Not specified"),
                "dataset": r.get("dataset", "Not specified"),
                "results": r.get("results", "Not specified"),
                "strengths": r.get("strengths", []),
                "limitations": r.get("limitations", []),
            }
        )

    prompt = f"""
You are the Compare Agent.

Given structured records for multiple papers, produce:
1) A concise markdown table with columns:
   Paper | Problem | Method | Dataset | Results | Strengths | Limitations
2) A section titled: "Aspect verdict: {aspect}"
   Rank papers from strongest to weakest for this aspect and give one-line reason per paper.

Structured records JSON:
{json.dumps(compact, ensure_ascii=False)}
"""

    try:
        return groq_chat(prompt, temperature=0.2).strip()
    except Exception:
        header = "| Paper | Problem | Method | Dataset | Results |\\n|---|---|---|---|---|"
        rows = [
            f"| {_markdown_cell(r.get('title'))} | {_markdown_cell(r.get('problem'))} | {_markdown_cell(r.get('method'))} | {_markdown_cell(r.get('dataset'))} | {_markdown_cell(r.get('results'))} |"
            for r in records
        ]
        fallback = "\n".join([header] + rows)
        fallback += f"\n\n### Aspect verdict: {aspect}\nUnable to produce ranked verdict due to a temporary model error."
        return fallback


def planner_agent_generate_insights(topic: str, records, comparison_markdown: str, aspect="overall quality"):
    """
    Planner Agent: synthesizes final insights and recommended next steps.
    """
    if not records:
        return "No records available for final planning insights."

    prompt = f"""
You are the Planner Agent for research analysis.

Using the structured records and comparison below, write a concise final report with sections:
1. Best Paper(s) for {aspect}
2. Common Trends Across Papers
3. Key Gaps and Limitations in Current Research
4. Suggested Next Reading / Next Experiments

Topic: {topic}

Structured records JSON:
{json.dumps(records, ensure_ascii=False)}

Comparison output:
{comparison_markdown[:5000]}
"""

    try:
        return groq_chat(prompt, temperature=0.25).strip()
    except Exception:
        return (
            "### Best Paper(s)\n"
            "Could not compute a reliable best-paper verdict right now.\n\n"
            "### Common Trends\n"
            "Most selected papers focus on similar problem framing with variations in methods.\n\n"
            "### Key Gaps and Limitations\n"
            "Abstract-only analysis can miss implementation details and hard metrics.\n\n"
            "### Suggested Next Steps\n"
            "Open full PDFs for top papers and re-run a deeper comparison with full-text evidence."
        )


def analyze_topic_multi_paper(topic: str, top_k: int = 3, aspect: str = "overall quality") -> dict:
    """
    End-to-end PoC pipeline:
    Search Agent -> Reader Agent -> Compare Agent -> Planner Agent
    """
    topic = str(topic or "").strip()
    if not topic:
        return {"error": "Topic is required."}

    selected_papers = search_agent_find_papers(topic, top_k=top_k)
    if len(selected_papers) < 2:
        return {"error": "Not enough papers with usable abstracts were found for this topic."}

    structured_records = []
    agent_log = [
        {
            "role": "Search Agent",
            "message": f"Found {len(selected_papers)} papers with usable abstracts for topic '{topic}'.",
        }
    ]

    for idx, paper in enumerate(selected_papers, start=1):
        structured = reader_agent_extract_structured(paper)
        structured_records.append(structured)
        agent_log.append(
            {
                "role": "Reader Agent",
                "message": f"Extracted structured fields for paper {idx}: {structured.get('title', 'Untitled')}",
            }
        )

    comparison_markdown = compare_agent_compare_structured(structured_records, aspect=aspect)
    agent_log.append(
        {
            "role": "Compare Agent",
            "message": f"Generated cross-paper matrix and ranking for aspect '{aspect}'.",
        }
    )

    insights_markdown = planner_agent_generate_insights(
        topic,
        structured_records,
        comparison_markdown,
        aspect=aspect,
    )
    agent_log.append(
        {
            "role": "Planner Agent",
            "message": "Generated final insights, research gaps, and suggested next steps.",
        }
    )

    return {
        "topic": topic,
        "aspect": aspect,
        "top_k": len(selected_papers),
        "papers": selected_papers,
        "structured": structured_records,
        "comparison_markdown": comparison_markdown,
        "insights_markdown": insights_markdown,
        "trace": {"agent_log": agent_log},
    }
