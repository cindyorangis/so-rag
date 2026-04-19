import re
from config import supabase, embedder, reranker


def sanitize_question(q: str) -> str:
    from fastapi import HTTPException
    q = q.strip()
    if not q:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    if len(q) > 500:
        raise HTTPException(status_code=400, detail="Question is too long (max 500 characters).")
    return q


def clean_for_fts(question: str) -> str:
    """Strip punctuation and join keywords for Postgres tsquery."""
    stop_words = {
        "what", "are", "the", "for", "a", "an", "do", "i", "how",
        "is", "to", "in", "of", "and", "or", "need", "get", "can",
    }
    words = re.sub(r"[^\w\s]", "", question.lower()).split()
    keywords = [w for w in words if w not in stop_words]
    return " & ".join(keywords) if keywords else ""


def embed_question(question: str) -> list:
    return embedder.encode(
        f"Represent this sentence for searching relevant passages: {question}"
    ).tolist()


async def hybrid_search(question: str, query_embedding: list, match_count: int) -> list:
    # Semantic search
    semantic = supabase.rpc("match_documents", {
        "query_embedding": query_embedding,
        "match_count": match_count,
    }).execute().data

    # Keyword search — only run if we have usable keywords
    keyword = []
    fts_query = clean_for_fts(question)
    if fts_query:
        keyword = (
            supabase.table("documents")
            .select("id, content, source, page_number, chunk_type, section_title, pdf_url")
            .text_search("fts", fts_query, options={"limit": match_count})
            .execute()
            .data
        )

    # Merge and deduplicate by id
    seen, merged = set(), []
    for row in semantic + keyword:
        if row["id"] not in seen:
            seen.add(row["id"])
            merged.append(row)

    return merged[: match_count + 4]


def rerank_chunks(question: str, chunks: list[dict], top_k: int = 6) -> list[dict]:
    pairs = [(question, c["content"]) for c in chunks]
    scores = reranker.predict(pairs)
    ranked = sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)

    # Limit to max 3 chunks per source for diversity
    seen_sources: dict[str, int] = {}
    diverse, remainder = [], []

    for score, chunk in ranked:
        source = chunk["source"]
        count = seen_sources.get(source, 0)
        if count < 3:
            seen_sources[source] = count + 1
            diverse.append(chunk)
        else:
            remainder.append(chunk)
        if len(diverse) == top_k:
            break

    # Fill remaining slots if we didn't hit top_k
    for chunk in remainder:
        if len(diverse) >= top_k:
            break
        diverse.append(chunk)

    return diverse


def build_context(chunks: list[dict]) -> str:
    blocks = [
        f"SOURCE {i + 1} [{c['source']} — Page {c['page_number']}]:\n{c['content']}"
        for i, c in enumerate(chunks)
    ]
    return "\n\n---\n\n".join(blocks)