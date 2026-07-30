"""
app/services/search.py
──────────────────────
Multi-source academic paper search.
Sources: Semantic Scholar API + arXiv Atom feed.
"""

import re
import concurrent.futures
from functools import lru_cache

import requests

from app.utils.text import _normalize_for_match, _parse_year, _title_match_score

MAX_RESULTS = 7


@lru_cache(maxsize=100)
def search_semantic_scholar(query, max_results=7):
    """Fetch papers from Semantic Scholar Graph API."""
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
    """Fetch papers from arXiv Atom API."""
    import xml.etree.ElementTree as ET

    url = "http://export.arxiv.org/api/query"
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results,
    }

    try:
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
                "source": "arXiv",
            })

        return papers

    except Exception:
        return []


def search_all_sources(query, max_results=7):
    """
    Parallel fetch from both sources, deduplicate, and rank by title
    relevance (exact → contains → token overlap), then citations and year.
    """
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
