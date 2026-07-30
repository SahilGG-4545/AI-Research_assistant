"""
app/services/report.py
──────────────────────
Report generation: per-paper academic reports and PDF summary reports.
"""

from core.llm import groq_chat


def generate_paper_report(paper: dict) -> str:
    """Generate a structured academic report for a single paper."""
    title = paper.get("title", "")
    authors = ", ".join(paper.get("authors", []))
    year = paper.get("year", "")
    venue = paper.get("venue", "")
    citations = paper.get("citations", 0)

    # SAFELY handle missing abstract
    raw_abs = paper.get("abstract")
    abstract = (raw_abs if isinstance(raw_abs, str) else "").strip()

    if not abstract:
        abstract = "The source provides no abstract for this paper."

    prompt = f"""
Produce a **clean academic report** for this paper.

Paper Title: {title}
Authors: {authors}
Year: {year}
Venue: {venue}
Citations: {citations}

Abstract:
{abstract}

Write the report with these sections:

1. Executive Summary
2. Key Contributions
3. Methodology
4. Strengths
5. Limitations
6. Applications
7. Future Work

Rules:
- If the abstract lacks detail, write naturally (e.g., "The abstract provides limited methodological detail.")
- Do NOT invent details.
- Do NOT repeat "not available" multiple times.
"""

    return groq_chat(prompt, temperature=0.35)


def generate_pdf_summary_report(full_text: str) -> str:
    """Generate a structured summary report of a PDF's extracted full text."""
    if not isinstance(full_text, str) or len(full_text.strip()) == 0:
        return "The PDF text is empty or unreadable."

    prompt = f"""
Summarize the following PDF text into a clean report.

Text:
{full_text[:8000]}

Write the report using these sections:

1. Executive Summary
2. Key Points
3. Important Definitions
4. Important Examples (if available)
5. Conclusion

Rules:
- Write in clear, concise academic format.
- Do NOT mention missing text.
- If information is limited, produce a short clean report.
"""

    return groq_chat(prompt, temperature=0.35)
