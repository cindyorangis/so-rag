import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from supabase import create_client
from sentence_transformers import SentenceTransformer, CrossEncoder
from groq import Groq
import re

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://so-rag.vercel.app"],
    allow_methods=["*"],
    allow_headers=["*"],
)

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_PUBLISHABLE_KEY"))
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
embedder = SentenceTransformer("BAAI/bge-base-en-v1.5")
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")


class AskRequest(BaseModel):
    question: str
    match_count: int = 12  # wider pool for reranker to work with


class Source(BaseModel):
    source: str
    page_number: int
    content: str


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]

def clean_for_fts(question: str) -> str:
    """Strip punctuation and join keywords for Postgres tsquery."""
    # Remove punctuation, lowercase, split into words
    words = re.sub(r"[^\w\s]", "", question.lower()).split()
    # Filter out common stop words Postgres can't handle
    stop_words = {"what", "are", "the", "for", "a", "an", "do", "i", "how",
                  "is", "to", "in", "of", "and", "or", "need", "get", "can"}
    keywords = [w for w in words if w not in stop_words]
    # Join with & for AND search
    return " & ".join(keywords) if keywords else ""

async def hybrid_search(question: str, query_embedding: list, match_count: int):
    # Semantic search
    semantic = supabase.rpc("match_documents", {
        "query_embedding": query_embedding,
        "match_count": match_count,
    }).execute().data

    # Keyword search — only run if we have usable keywords
    keyword = []
    fts_query = clean_for_fts(question)
    if fts_query:
        keyword = supabase.table("documents") \
            .select("id, content, source, page_number") \
            .text_search("fts", fts_query, options={"limit": match_count}) \
            .execute().data

    # Merge and deduplicate by id
    seen, merged = set(), []
    for row in (semantic + keyword):
        if row["id"] not in seen:
            seen.add(row["id"])
            merged.append(row)

    return merged[:match_count + 4]

def rerank(question: str, chunks: list[dict], top_k: int = 6) -> list[dict]:
    pairs = [(question, c["content"]) for c in chunks]
    scores = reranker.predict(pairs)
    ranked = sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)
    return [chunk for _, chunk in ranked[:top_k]]


@app.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest):
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        # 1. Embed the question (BGE prefix for retrieval)
        query_embedding = embedder.encode(
            f"Represent this sentence for searching relevant passages: {body.question}"
        ).tolist()

        # 2. Hybrid search — semantic + keyword, deduplicated
        candidates = await hybrid_search(body.question, query_embedding, body.match_count)

        if not candidates:
            return AskResponse(
                answer="I'm sorry, I couldn't find any information regarding that in the available ServiceOntario manuals.",
                sources=[]
            )

        # 3. Rerank candidates, keep top 6 for the LLM
        reranked = rerank(body.question, candidates, top_k=6)

        # 4. Build context from reranked chunks
        context_blocks = []
        for i, c in enumerate(reranked):
            block = f"SOURCE {i+1} [{c['source']} — Page {c['page_number']}]:\n{c['content']}"
            context_blocks.append(block)

        context = "\n\n---\n\n".join(context_blocks)

        # 5. Ask Groq
        system_prompt = (
            "You are a professional ServiceOntario Support Assistant. "
            "Your goal is to provide accurate information based ONLY on the provided manual excerpts.\n\n"
            "FORMATTING:\n"
            "- Always use proper markdown: **bold**, `code`, and - for bullet lists\n"
            "- Never use • unicode bullets — use - instead\n"
            "- Use nested lists with two spaces of indentation for sub-items\n\n"
            "RULES:\n"
            "1. Base every claim on a provided source. If not covered, say: \"This isn't covered in the available manuals.\"\n"
            "2. When quoting fees, form numbers, or requirements, cite the manual and page: e.g. (Vehicle Registration Manual, p. 12)\n"
            "3. Tables contain fees and eligibility — read the column headers carefully before extracting values.\n"
            "4. Use bullet points for multi-step processes or lists of requirements.\n"
            "5. If multiple sources conflict, note the discrepancy and cite both.\n"
            "6. Never invent fees, form numbers, or deadlines."
        )

        user_prompt = f"CONTEXT:\n{context}\n\nQUESTION: {body.question}"

        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,
            max_tokens=800,
        )

        answer = completion.choices[0].message.content.strip()

        # 6. Deduplicate sources from reranked chunks for the UI
        seen_sources = set()
        unique_sources = []
        for c in reranked:
            source_id = f"{c['source']}-{c['page_number']}"
            if source_id not in seen_sources:
                seen_sources.add(source_id)
                unique_sources.append(Source(
                    source=c["source"],
                    page_number=c["page_number"],
                    content=c["content"]
                ))

        return AskResponse(answer=answer, sources=unique_sources)

    except Exception as e:
        print(f"Error during /ask: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred processing your request.")


@app.get("/health")
def health():
    return {"status": "ok"}