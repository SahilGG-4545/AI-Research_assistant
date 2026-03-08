# ============================================================
#  RESEARCH ASSISTANT (Stable Clean Version)
#  Multi-source search (Semantic Scholar + arXiv)
#  PDF RAG Q&A • Code Gen • Chatbot • Paper Reports
# ============================================================

import os
import requests
from PyPDF2 import PdfReader
from autogen import AssistantAgent, UserProxyAgent
from dotenv import load_dotenv
from groq import Groq
import concurrent.futures
from functools import lru_cache

# ============================================================
# 1. LOAD ENVIRONMENT + INIT GROQ
# ============================================================

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise ValueError("❌ GROQ_API_KEY missing in .env")

client = Groq(api_key=GROQ_API_KEY)

# ============================================================
# 2. GROQ CHAT WRAPPER
# ============================================================

def groq_chat(prompt: str, model="llama-3.3-70b-versatile",
              conversation_history=None, temperature=0.4):

    messages = []
    if conversation_history:
        messages.extend(conversation_history)

    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=1800,
    )

    return response.choices[0].message.content


# ============================================================
# 3. AUTOGEN AGENTS (NO DOCKER)
# ============================================================

NO_DOCKER = {"use_docker": False}

controller_agent = UserProxyAgent(
    name="controller",
    system_message="Coordinates processing across agents.",
    code_execution_config=NO_DOCKER,
    human_input_mode="NEVER",
)

search_agent = AssistantAgent(
    name="search_agent",
    system_message="Retrieve academic papers.",
    code_execution_config=NO_DOCKER,
)

qa_agent = AssistantAgent(
    name="qa_agent",
    system_message="Answer questions using provided context only.",
    code_execution_config=NO_DOCKER,
)

code_agent = AssistantAgent(
    name="code_agent",
    system_message="Generate production-grade code.",
    code_execution_config=NO_DOCKER,
)

# ============================================================
# 4. PAPER SEARCH — ONLY ARXIV + SEMANTIC SCHOLAR
# ============================================================

MAX_RESULTS = 7


@lru_cache(maxsize=100)
def search_semantic_scholar(query, max_results=7):

    url = (
        "https://api.semanticscholar.org/graph/v1/paper/search?"
        f"query={query}&limit={max_results}&"
        "fields=title,abstract,authors,year,citationCount,url,venue"
    )

    try:
        res = requests.get(url, timeout=10).json()
        papers = []

        for p in res.get("data", []):
            abs_raw = p.get("abstract")
            abstract = abs_raw if isinstance(abs_raw, str) else ""

            papers.append({
                "title": p.get("title", ""),
                "abstract": abstract,
                "authors": [a["name"] for a in p.get("authors", [])],
                "url": p.get("url", ""),

            })

        return papers

    except Exception:
        return []


@lru_cache(maxsize=100)
def search_arxiv(query, max_results=7):
    url = f"http://export.arxiv.org/api/query?search_query=all:{query}&start=0&max_results={max_results}"

    try:
        import xml.etree.ElementTree as ET

        res = requests.get(url, timeout=10)
        root = ET.fromstring(res.content)
        papers = []

        for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
            title = (entry.find('{http://www.w3.org/2005/Atom}title').text or "").strip()
            summary = (entry.find('{http://www.w3.org/2005/Atom}summary').text or "").strip()

            authors = [
                a.find('{http://www.w3.org/2005/Atom}name').text
                for a in entry.findall('{http://www.w3.org/2005/Atom}author')
            ]

            link = entry.find('{http://www.w3.org/2005/Atom}id').text
            year = entry.find('{http://www.w3.org/2005/Atom}published').text[:4]

            papers.append({
                "title": title,
                "abstract": summary,
                "authors": authors,
                "year": year,
                "citations": 0,
                "url": link,
                "venue": "arXiv",
                "source": "arXiv"
            })

        return papers

    except Exception:
        return []


def search_all_sources(query, max_results=7):

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        sem_future = ex.submit(search_semantic_scholar, query, max_results)
        arxiv_future = ex.submit(search_arxiv, query, max_results)

        sem_res = sem_future.result()
        arxiv_res = arxiv_future.result()

    combined = sem_res + arxiv_res

    seen = set()
    unique = []

    for p in combined:
        key = p["title"].lower().strip()
        if key and key not in seen:
            unique.append(p)
            seen.add(key)

    # Sort by citations then year
    unique.sort(key=lambda x: (x.get("citations", 0), str(x.get("year", ""))), reverse=True)

    return unique[:MAX_RESULTS]


# ============================================================
# 5. PDF CHUNKING + CLEAN RAG Q&A
# ============================================================

def extract_pdf_text_chunked(pdf_file, chunk_size=1000, overlap=200):

    reader = PdfReader(pdf_file)
    text = ""

    for page in reader.pages:
        t = page.extract_text()
        if t:
            text += t + "\n"

    clean = " ".join(text.split())

    chunks = []
    start = 0

    while start < len(clean):
        end = start + chunk_size
        chunks.append(clean[start:end])
        start += chunk_size - overlap

    return {"full_text": clean, "chunks": chunks}


def find_relevant_chunks(chunks, question, top_k=3):

    terms = set(question.lower().split())
    scored = []

    for c in chunks:
        score = sum(t in c.lower() for t in terms)
        scored.append((score, c))

    scored.sort(reverse=True)

    return [c for s, c in scored[:top_k] if s > 0]


def answer_with_rag(chunks, question):

    relevant = find_relevant_chunks(chunks, question)

    if not relevant:
        return "The document does not contain information related to this question."

    context = "\n\n".join(c[:600] for c in relevant)

    prompt = f"""
Use ONLY the context below.

Context:
{context}

Question:
{question}

Answer clearly:
"""

    return groq_chat(prompt).strip()


# ============================================================
# 6. PAPER REPORT (FULLY FIXED — NO MORE CRASHING)
# ============================================================

def generate_paper_report(paper: dict) -> str:

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


# ============================================================
# 7. PAPER QUESTION ANSWERING (SAFE)
# ============================================================

def answer_question_about_selected_paper(paper: dict, question: str, history=None):

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


# ============================================================
# 8. GENERAL CHATBOT
# ============================================================

def chatbot_answer(prompt, history=None):
    return groq_chat(prompt, conversation_history=history)


# ============================================================
# 9. CODE GENERATOR
# ============================================================

def generate_advanced_code(instruction: str, language: str = "python") -> str:

    prompt = f"""
Write {language} code for:

{instruction}

Rules:
- ONLY code (no explanation)
- Include comments
- Use clean structure
- Handle errors gracefully
"""

    result = groq_chat(prompt, temperature=0.2)
    return result.strip()


# ============================================================
# 10. PAPER COMPARISON
# ============================================================

def compare_two_papers_rag(text1, text2, aspect):

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
def generate_pdf_summary_report(full_text: str) -> str:
    """
    Generates a structured summary report of a PDF's extracted full text.
    """

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


