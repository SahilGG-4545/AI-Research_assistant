# ============================================================
#  RESEARCH ASSISTANT (Stable Clean Version)
#  Multi-source search (Semantic Scholar + arXiv)
#  PDF RAG Q&A • Code Gen • Chatbot • Paper Reports
# ============================================================

import os
import re
import json
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


def _normalize_for_match(text: str) -> str:
    clean = re.sub(r"[^a-z0-9\s]", " ", str(text or "").lower())
    return " ".join(clean.split()).strip()


def _parse_year(value) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    match = re.search(r"\d{4}", text)
    if not match:
        return 0
    try:
        return int(match.group(0))
    except Exception:
        return 0


def _title_match_score(title: str, query: str):
    norm_title = _normalize_for_match(title)
    norm_query = _normalize_for_match(query)

    if not norm_title or not norm_query:
        return (0, 0, 0.0)

    exact = 1 if norm_title == norm_query else 0
    contains = 1 if norm_query in norm_title else 0

    query_tokens = set(norm_query.split())
    title_tokens = set(norm_title.split())
    overlap = (len(query_tokens & title_tokens) / len(query_tokens)) if query_tokens else 0.0

    return (exact, contains, overlap)


@lru_cache(maxsize=100)
def search_semantic_scholar(query, max_results=7):

    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": max_results,
        "fields": "title,abstract,authors,year,citationCount,url,venue",
    }

    try:
        res = requests.get(url, params=params, timeout=10).json()
        papers = []

        for p in res.get("data", []):
            abs_raw = p.get("abstract")
            abstract = abs_raw if isinstance(abs_raw, str) else ""

            papers.append({
                "title": p.get("title", ""),
                "abstract": abstract,
                "authors": [a["name"] for a in p.get("authors", [])],
                "year": p.get("year", ""),
                "citations": p.get("citationCount", 0),
                "venue": p.get("venue", ""),
                "url": p.get("url", ""),
                "source": "Semantic Scholar",

            })

        return papers

    except Exception:
        return []


@lru_cache(maxsize=100)
def search_arxiv(query, max_results=7):
    url = "http://export.arxiv.org/api/query"
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results,
    }

    try:
        import xml.etree.ElementTree as ET

        res = requests.get(url, params=params, timeout=10)
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

    try:
        final_k = max(1, int(max_results))
    except Exception:
        final_k = MAX_RESULTS

    # Fetch a wider pool, then keep top-k after ranking.
    fetch_per_source = max(20, final_k * 4)

    exact_query = f'"{str(query).strip()}"'

    # Combine broad retrieval with exact-phrase retrieval for title queries.
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        sem_future = ex.submit(search_semantic_scholar, query, fetch_per_source)
        sem_exact_future = ex.submit(search_semantic_scholar, exact_query, max(5, final_k))
        arxiv_future = ex.submit(search_arxiv, query, fetch_per_source)
        arxiv_exact_future = ex.submit(search_arxiv, exact_query, max(5, final_k))

        sem_res = sem_future.result()
        sem_exact_res = sem_exact_future.result()
        arxiv_res = arxiv_future.result()
        arxiv_exact_res = arxiv_exact_future.result()

    combined = sem_res + sem_exact_res + arxiv_res + arxiv_exact_res

    seen = set()
    unique = []

    for p in combined:
        key = _normalize_for_match(p.get("title", ""))
        if key and key not in seen:
            unique.append(p)
            seen.add(key)

    # Rank by title relevance first (exact/contains/token overlap), then citations and year.
    unique.sort(
        key=lambda x: (
            *_title_match_score(x.get("title", ""), query),
            int(x.get("citations", 0) or 0),
            _parse_year(x.get("year", "")),
        ),
        reverse=True,
    )

    return unique[:final_k]


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


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _tokenize_for_bm25(text: str):
    return re.findall(r"\b\w+\b", text.lower())


def _rewrite_query_for_retrieval(question: str) -> str:
    if not _env_flag("RAG_QUERY_REWRITE", default=True):
        return question

    prompt = f"""
Rewrite this question into one short search query for technical document retrieval.
Keep intent unchanged.
Return only one line.

Question: {question}
"""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=80,
        )
        rewritten = (response.choices[0].message.content or "").strip()
        if not rewritten:
            return question
        return rewritten.splitlines()[0].strip() or question
    except Exception:
        return question


def _rrf_fuse_rankings(rank_lists, top_k=4, k=60):
    fused_scores = {}

    for rank_list in rank_lists:
        for rank, chunk_idx in enumerate(rank_list, start=1):
            fused_scores[chunk_idx] = fused_scores.get(chunk_idx, 0.0) + (1.0 / (k + rank))

    ranked = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
    return [chunk_idx for chunk_idx, _ in ranked[:top_k]]


def _rerank_chunk_indices(question: str, chunks, chunk_indices, top_k=4):
    if not _env_flag("RAG_USE_RERANK", default=False):
        return chunk_indices[:top_k], False

    try:
        from sentence_transformers import CrossEncoder
    except Exception:
        return chunk_indices[:top_k], False

    model_name = os.getenv("RAG_RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

    try:
        reranker = CrossEncoder(model_name)
        pairs = [(question, chunks[idx]) for idx in chunk_indices]
        scores = reranker.predict(pairs, show_progress_bar=False)
        ranked = sorted(zip(chunk_indices, scores), key=lambda x: float(x[1]), reverse=True)
        return [chunk_idx for chunk_idx, _ in ranked[:top_k]], True
    except Exception:
        return chunk_indices[:top_k], False


def find_relevant_chunks_hybrid(chunks, question, top_k=4, bm25_k=8, dense_k=8, return_trace=False):
    trace = {
        "query_original": question,
        "query_used": question,
        "query_rewritten": False,
        "rerank_used": False,
        "stage_top_chunks": {
            "bm25": [],
            "dense": [],
            "rrf": [],
            "final": [],
        },
        "final_chunk_snippets": [],
    }

    if not chunks:
        return ([], trace) if return_trace else []

    query = _rewrite_query_for_retrieval(question)
    trace["query_used"] = query
    trace["query_rewritten"] = query.strip().lower() != question.strip().lower()

    try:
        import chromadb
        from chromadb.config import Settings
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        from rank_bm25 import BM25Okapi
    except Exception:
        return ([], trace) if return_trace else []

    tokenized_corpus = [_tokenize_for_bm25(chunk) for chunk in chunks]
    bm25 = BM25Okapi(tokenized_corpus)
    query_tokens = _tokenize_for_bm25(query)
    bm25_scores = bm25.get_scores(query_tokens) if query_tokens else [0.0] * len(chunks)
    bm25_ranked = [
        idx
        for idx, _ in sorted(
            enumerate(bm25_scores),
            key=lambda x: float(x[1]),
            reverse=True,
        )[:bm25_k]
    ]
    trace["stage_top_chunks"]["bm25"] = bm25_ranked[:]

    dense_ranked = []
    try:
        embedding_model = os.getenv(
            "RAG_EMBEDDING_MODEL",
            "sentence-transformers/all-MiniLM-L6-v2",
        )
        chroma_client = chromadb.EphemeralClient(
            settings=Settings(anonymized_telemetry=False),
        )
        collection = chroma_client.create_collection(
            name="tmp_rag_collection",
            embedding_function=SentenceTransformerEmbeddingFunction(model_name=embedding_model),
            metadata={"hnsw:space": "cosine"},
        )

        ids = [f"chunk-{i}" for i in range(len(chunks))]
        metadatas = [{"chunk_index": i} for i in range(len(chunks))]
        collection.add(ids=ids, documents=chunks, metadatas=metadatas)

        dense_response = collection.query(
            query_texts=[query],
            n_results=min(dense_k, len(chunks)),
            include=["metadatas"],
        )
        dense_ranked = [
            int(meta.get("chunk_index", 0))
            for meta in dense_response.get("metadatas", [[]])[0]
        ]
    except Exception:
        dense_ranked = []

    trace["stage_top_chunks"]["dense"] = dense_ranked[:]

    rank_lists = []
    if bm25_ranked:
        rank_lists.append(bm25_ranked)
    if dense_ranked:
        rank_lists.append(dense_ranked)

    if not rank_lists:
        return ([], trace) if return_trace else []

    fused_indices = _rrf_fuse_rankings(rank_lists, top_k=max(top_k, 6), k=60)
    trace["stage_top_chunks"]["rrf"] = fused_indices[:]
    fused_indices, rerank_used = _rerank_chunk_indices(query, chunks, fused_indices, top_k=top_k)
    trace["rerank_used"] = rerank_used
    trace["stage_top_chunks"]["final"] = fused_indices[:]

    trace["final_chunk_snippets"] = [
        chunks[idx][:180] for idx in fused_indices if 0 <= idx < len(chunks)
    ]

    selected_chunks = [chunks[idx] for idx in fused_indices if 0 <= idx < len(chunks)]

    if return_trace:
        return selected_chunks, trace

    return selected_chunks


def _find_relevant_chunks_keyword_with_indices(chunks, question, top_k=3):

    terms = set(question.lower().split())
    scored = []

    for idx, c in enumerate(chunks):
        score = sum(t in c.lower() for t in terms)
        scored.append((score, idx, c))

    scored.sort(reverse=True)
    selected = [(idx, c) for score, idx, c in scored[:top_k] if score > 0]

    return [c for idx, c in selected], [idx for idx, c in selected]


def find_relevant_chunks(chunks, question, top_k=3):
    selected_chunks, _ = _find_relevant_chunks_keyword_with_indices(chunks, question, top_k=top_k)
    return selected_chunks


def answer_with_rag(chunks, question, with_trace=False):

    try:
        final_top_k = max(1, int(os.getenv("RAG_FINAL_TOP_K", "4")))
    except ValueError:
        final_top_k = 4

    trace = {
        "mode_requested": "hybrid" if _env_flag("RAG_USE_HYBRID", default=True) else "baseline",
        "mode_used": "none",
        "fallback_used": False,
        "query_original": question,
        "query_used": question,
        "query_rewritten": False,
        "rerank_used": False,
        "chunk_count_total": len(chunks),
        "chunk_count_selected": 0,
        "stage_top_chunks": {
            "bm25": [],
            "dense": [],
            "rrf": [],
            "final": [],
        },
        "final_chunk_snippets": [],
    }

    # Hybrid retrieval is primary and baseline keyword overlap is fallback.
    relevant = []
    if _env_flag("RAG_USE_HYBRID", default=True):
        relevant, hybrid_trace = find_relevant_chunks_hybrid(
            chunks,
            question,
            top_k=final_top_k,
            return_trace=True,
        )
        trace.update(hybrid_trace)
        if relevant:
            trace["mode_used"] = "hybrid"

    if not relevant:
        fallback_chunks, fallback_indices = _find_relevant_chunks_keyword_with_indices(
            chunks,
            question,
            top_k=max(3, final_top_k),
        )
        relevant = fallback_chunks
        trace["mode_used"] = "baseline"
        trace["fallback_used"] = _env_flag("RAG_USE_HYBRID", default=True)
        trace["query_used"] = question
        trace["query_rewritten"] = False
        trace["rerank_used"] = False
        trace["stage_top_chunks"] = {
            "bm25": [],
            "dense": [],
            "rrf": [],
            "final": fallback_indices,
        }
        trace["final_chunk_snippets"] = [
            chunks[idx][:180] for idx in fallback_indices if 0 <= idx < len(chunks)
        ]

    if not relevant:
        message = "The document does not contain information related to this question."
        if with_trace:
            return {"answer": message, "trace": trace}
        return message

    trace["chunk_count_selected"] = len(relevant)

    context = "\n\n".join(c[:600] for c in relevant)

    prompt = f"""
Use ONLY the context below.

Context:
{context}

Question:
{question}

Answer clearly:
"""

    answer_text = groq_chat(prompt).strip()

    if with_trace:
        return {"answer": answer_text, "trace": trace}

    return answer_text


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
# ============================================================
# 8. CODE GENERATOR
# ============================================================

def generate_advanced_code(instruction: str, language: str = "python") -> dict:
    """
    Simulates a multi-agent Code Generation & Review Squad by storing
    and passing a conversational log between a Developer and a QA Reviewer.
    """
    chat_log = []
    
    # --- 1. DEVELOPER AGENT ---
    dev_prompt = f"""
You are an expert {language} Developer. The user wants to build: "{instruction}".
Write the code, explain your thought process briefly, and directly ask the "QA Reviewer" to check it for bugs or improvements.
Make it sound like a real conversation.
"""
    dev_response = groq_chat(dev_prompt, temperature=0.5).strip()
    chat_log.append({"role": "Developer 🧑‍💻", "message": dev_response})

    # --- 2. QA/REVIEWER AGENT ---
    qa_prompt = f"""
You are the QA and Security Reviewer. The Developer just sent you this message:

"{dev_response}"

Talk directly back to the Developer. Point out any missing edge cases, security flaws, or inefficiencies in their code. Suggest fixes in a conversational tone.
If it's perfect, just say "Looks great to me."
"""
    qa_review = groq_chat(qa_prompt, temperature=0.3).strip()
    chat_log.append({"role": "QA Reviewer 🕵️", "message": qa_review})

    # --- 3. LEAD DEVELOPER AGENT (Final Fix) ---
    lead_prompt = f"""
You are the Developer again. You wrote this:
"{dev_response}"

The QA Reviewer replied with:
"{qa_review}"

Reply to the Reviewer, thank them (or agree/disagree), and then provide the FINAL fixed {language} code. 
IMPORTANT: Put the final code inside standard markdown blocks like ```{language} ... ``` so it can be extracted.
"""
    final_response = groq_chat(lead_prompt, temperature=0.3).strip()
    chat_log.append({"role": "Developer 🧑‍💻", "message": final_response})
    
    # Extract code from the final response
    code_match = re.search(r"```(?:\w+)?\n(.*?)```", final_response, re.DOTALL)
    if code_match:
        final_code = code_match.group(1).strip()
    else:
        # Fallback cleanup
        final_code = re.sub(r"^```[\w]*\n?", "", final_response, flags=re.MULTILINE)
        final_code = re.sub(r"\n?```$", "", final_code).strip()
        
    return {"code": final_code, "trace": {"chat_log": chat_log}}


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


def _extract_json_object(text: str) -> dict:
    if not isinstance(text, str):
        return {}

    payload = text.strip()
    if not payload:
        return {}

    try:
        parsed = json.loads(payload)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", payload)
    if not match:
        return {}

    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _normalize_string_list(value, fallback="Not clearly stated in abstract."):
    if isinstance(value, list):
        cleaned = [str(v).strip() for v in value if str(v).strip()]
    elif isinstance(value, str):
        parts = re.split(r"\n|;|,", value)
        cleaned = [p.strip(" -") for p in parts if p.strip()]
    else:
        cleaned = []

    if not cleaned:
        return [fallback]

    return cleaned[:5]


def _clean_text_value(value, fallback="Not specified"):
    if isinstance(value, str):
        text = " ".join(value.split()).strip()
    else:
        text = str(value).strip() if value is not None else ""
    return text if text else fallback


def _markdown_cell(value, max_len=140):
    text = _clean_text_value(value, fallback="-")
    if len(text) > max_len:
        text = text[: max_len - 3].rstrip() + "..."
    return text.replace("|", "/")


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


