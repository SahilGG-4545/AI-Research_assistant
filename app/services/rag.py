"""
app/services/rag.py
────────────────────
PDF text extraction + hybrid retrieval (BM25 + dense + RRF) + RAG Q&A.
"""

import os
import re

from PyPDF2 import PdfReader

from core.config import _env_flag
from core.llm import client, groq_chat


# ──────────────────────────────────────────────────────────────
# PDF EXTRACTION
# ──────────────────────────────────────────────────────────────

def extract_pdf_text_chunked(pdf_file, chunk_size=1000, overlap=200):
    """Extract all text from a PDF and return full text + sliding-window chunks."""
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


# ──────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ──────────────────────────────────────────────────────────────

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


# ──────────────────────────────────────────────────────────────
# HYBRID RETRIEVAL
# ──────────────────────────────────────────────────────────────

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


# ──────────────────────────────────────────────────────────────
# RAG Q&A
# ──────────────────────────────────────────────────────────────

def answer_with_rag(chunks, question, with_trace=False):
    """
    Answer a question using hybrid retrieval over PDF chunks.
    Falls back to baseline keyword overlap when hybrid retrieval yields nothing.
    """
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
