"""
Simple RAG test script (separate from Flask app).

Purpose:
- Keep experimentation easy for a beginner.
- Test retrieval quality in terminal.
- Do not touch production Flask code.
"""

import os
import re
import textwrap
from pathlib import Path

import chromadb
from chromadb.config import Settings
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from dotenv import load_dotenv
from groq import Groq
from langchain_text_splitters import RecursiveCharacterTextSplitter
from PyPDF2 import PdfReader
from rank_bm25 import BM25Okapi


# ---------------------------
# 1) EASY SETTINGS (EDIT ME)
# ---------------------------
PDF_PATH = "research_paper.pdf"
QUESTION = "How does the system handle emergency vehicles like ambulances?"  # Change this question anytime.

CHUNK_SIZE = 900
CHUNK_OVERLAP = 150
TOP_K_BM25 = 8
TOP_K_DENSE = 8
TOP_K_FINAL = 4

USE_QUERY_REWRITE = False
USE_RERANK = False
GENERATE_ANSWER = False

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
GROQ_MODEL = "llama-3.3-70b-versatile"
CHROMA_PATH = ".rag_lab_chroma"
COLLECTION_NAME = "rag_lab_simple"


def get_groq_client() -> Groq | None:
    """Returns Groq client if GROQ_API_KEY exists, otherwise None."""
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return None
    return Groq(api_key=api_key)


def read_pdf_text(pdf_path: Path) -> str:
    """Extract and normalize text from a PDF file."""
    reader = PdfReader(str(pdf_path))
    text_parts = []

    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            text_parts.append(page_text)

    return " ".join("\n".join(text_parts).split())


def chunk_text(text: str) -> list[str]:
    """Split document into overlapping chunks for retrieval."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return [chunk.strip() for chunk in splitter.split_text(text) if chunk.strip()]


def tokenize(text: str) -> list[str]:
    """Simple tokenizer for BM25."""
    return re.findall(r"\b\w+\b", text.lower())


def build_indexes(chunks: list[str]) -> tuple[BM25Okapi, any]:
    """Build BM25 index and Chroma dense index."""
    # BM25 (keyword retrieval)
    tokenized_corpus = [tokenize(chunk) for chunk in chunks]
    bm25_index = BM25Okapi(tokenized_corpus)

    # Chroma (dense retrieval)
    chroma_client = chromadb.PersistentClient(
        path=CHROMA_PATH,
        settings=Settings(anonymized_telemetry=False),
    )

    # Start fresh each run to keep behavior simple and predictable.
    try:
        chroma_client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    embedding_fn = SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
    collection = chroma_client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )

    ids = [f"chunk-{i}" for i in range(len(chunks))]
    metadata = [{"chunk_index": i} for i in range(len(chunks))]
    collection.add(ids=ids, documents=chunks, metadatas=metadata)

    return bm25_index, collection


def retrieve_bm25(bm25_index: BM25Okapi, chunks: list[str], query: str, top_k: int) -> list[tuple[int, float]]:
    """Return top chunk indexes from BM25."""
    query_tokens = tokenize(query)
    scores = bm25_index.get_scores(query_tokens) if query_tokens else [0.0] * len(chunks)
    ranked = sorted(enumerate(scores), key=lambda x: float(x[1]), reverse=True)
    return [(idx, float(score)) for idx, score in ranked[:top_k]]


def retrieve_dense(collection: any, chunks: list[str], query: str, top_k: int) -> list[tuple[int, float]]:
    """Return top chunk indexes from dense vector search."""
    result = collection.query(
        query_texts=[query],
        n_results=min(top_k, len(chunks)),
        include=["metadatas", "distances"],
    )

    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]

    hits = []
    for i, meta in enumerate(metadatas):
        idx = int(meta.get("chunk_index", i))
        distance = float(distances[i]) if i < len(distances) else 1.0
        similarity = 1.0 - distance
        hits.append((idx, similarity))

    return hits


def rrf_fusion(rank_lists: list[list[tuple[int, float]]], top_k: int, k: int = 60) -> list[tuple[int, float]]:
    """
    Reciprocal Rank Fusion (RRF).
    We only use item rank, not raw score, to combine systems fairly.
    """
    fused_scores: dict[int, float] = {}

    for rank_list in rank_lists:
        for rank, (chunk_idx, _score) in enumerate(rank_list, start=1):
            fused_scores[chunk_idx] = fused_scores.get(chunk_idx, 0.0) + (1.0 / (k + rank))

    ranked = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
    return ranked[:top_k]


def rewrite_query(client: Groq | None, query: str) -> str:
    """Optional query rewrite with Groq for better recall."""
    if client is None:
        return query

    prompt = f"""
Rewrite this user question into one short search query for technical retrieval.
Keep intent same. Return only rewritten query.

Question: {query}
"""

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=80,
    )
    rewritten = (response.choices[0].message.content or "").strip()
    return rewritten or query


def rerank_hits(query: str, chunks: list[str], hits: list[tuple[int, float]], top_k: int) -> list[tuple[int, float]]:
    """Optional reranking with cross-encoder model."""
    from sentence_transformers import CrossEncoder

    model = CrossEncoder(RERANK_MODEL)
    pairs = [(query, chunks[idx]) for idx, _score in hits]
    scores = model.predict(pairs, show_progress_bar=False)

    combined = [(hits[i][0], float(scores[i])) for i in range(len(hits))]
    return sorted(combined, key=lambda x: x[1], reverse=True)[:top_k]


def print_hits(title: str, hits: list[tuple[int, float]], chunks: list[str]) -> None:
    """Pretty print retrieval results."""
    print(f"\n=== {title} ===")
    if not hits:
        print("No results.")
        return

    for rank, (idx, score) in enumerate(hits, start=1):
        preview = textwrap.shorten(chunks[idx].replace("\n", " "), width=190, placeholder="...")
        print(f"{rank}. chunk={idx} score={score:.4f}")
        print(f"   {preview}")


def answer_from_context(client: Groq | None, query: str, chunks: list[str], final_hits: list[tuple[int, float]]) -> str:
    """Optional final answer generation using selected chunks only."""
    if client is None:
        return "GROQ_API_KEY not found. Skipping answer generation."

    context = "\n\n".join([f"[Chunk {idx}] {chunks[idx][:900]}" for idx, _score in final_hits])

    prompt = f"""
Use ONLY the context below to answer the question.

Context:
{context}

Question:
{query}

If answer is missing in context, reply:
"The retrieved context does not contain the answer."
"""

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=700,
    )
    return (response.choices[0].message.content or "").strip()


def main() -> None:
    # 1) Validate easy settings
    pdf_path = Path(PDF_PATH)
    if not pdf_path.exists():
        raise SystemExit(f"PDF not found: {pdf_path}")

    if not QUESTION.strip():
        raise SystemExit("QUESTION is empty. Please write a question at top of file.")

    # 2) Read and chunk PDF
    print("Loading PDF...")
    full_text = read_pdf_text(pdf_path)
    chunks = chunk_text(full_text)

    if not chunks:
        raise SystemExit("No text extracted from PDF.")

    print(f"PDF: {pdf_path}")
    print(f"Characters: {len(full_text)}")
    print(f"Chunks: {len(chunks)}")

    # 3) Optional query rewrite
    groq_client = get_groq_client()
    effective_query = QUESTION
    if USE_QUERY_REWRITE:
        effective_query = rewrite_query(groq_client, QUESTION)

    print("\nQuery")
    print(f"Original : {QUESTION}")
    print(f"Used     : {effective_query}")

    # 4) Build retrieval indexes
    bm25_index, collection = build_indexes(chunks)

    # 5) Retrieve with BM25 and dense search
    bm25_hits = retrieve_bm25(bm25_index, chunks, effective_query, TOP_K_BM25)
    dense_hits = retrieve_dense(collection, chunks, effective_query, TOP_K_DENSE)

    # 6) Fuse rankings with RRF
    fused_hits = rrf_fusion([bm25_hits, dense_hits], top_k=max(TOP_K_FINAL, 6))
    final_hits = fused_hits[:TOP_K_FINAL]

    # 7) Optional reranking step
    if USE_RERANK:
        try:
            final_hits = rerank_hits(effective_query, chunks, fused_hits, TOP_K_FINAL)
        except Exception as exc:
            print(f"\nRerank skipped: {exc}")

    # 8) Print retrieval results
    print_hits("BM25 results", bm25_hits, chunks)
    print_hits("Dense results", dense_hits, chunks)
    print_hits("RRF fused results", fused_hits, chunks)

    if USE_RERANK:
        print_hits("Final reranked results", final_hits, chunks)
    else:
        print_hits("Final selected results", final_hits, chunks)

    # 9) Optional answer generation
    if GENERATE_ANSWER:
        answer = answer_from_context(groq_client, effective_query, chunks, final_hits)
        print("\n=== Answer ===")
        print(answer)


if __name__ == "__main__":
    main()
