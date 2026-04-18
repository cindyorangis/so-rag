import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from supabase import create_client
from sentence_transformers import SentenceTransformer, CrossEncoder
from groq import Groq, RateLimitError
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
    
    # Ensure we don't over-represent a single source
    seen_sources = {}
    diverse = []
    remainder = []
    
    for score, chunk in ranked:
        source = chunk["source"]
        count = seen_sources.get(source, 0)
        if count < 2:  # max 2 chunks per source
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
        reranked = rerank(body.question, candidates, top_k=8)

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
            "1. Check ALL provided sources before answering — do not stop at the first relevant one.\n"
            "2. If multiple manuals cover the topic, synthesize all of them in your answer.\n"
            "3. If a source is only partially relevant, still extract what applies.\n"
            "4. Base every claim on a provided source. If not covered, say: \"This isn't covered in the available manuals.\"\n"
            "5. When quoting fees, form numbers, or requirements, cite the manual and page: e.g. (Vehicle Registration Manual, p. 12)\n"
            "6. Tables contain fees and eligibility — read the column headers carefully before extracting values.\n"
            "7. Use bullet points for multi-step processes or lists of requirements.\n"
            "8. If multiple sources conflict, note the discrepancy and cite both.\n"
            "9. Never invent fees, form numbers, or deadlines."
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
    
    except RateLimitError as e:
        print(f"Groq 429 Rate Limit Hit")
        print(f"  Error: {e.message}")
        if hasattr(e, 'response') and e.response is not None:
            headers = e.response.headers
            print(f"  Limit (req/min):   {headers.get('x-ratelimit-limit-requests', 'N/A')}")
            print(f"  Remaining req:     {headers.get('x-ratelimit-remaining-requests', 'N/A')}")
            print(f"  Limit (tok/min):   {headers.get('x-ratelimit-limit-tokens', 'N/A')}")
            print(f"  Remaining tokens:  {headers.get('x-ratelimit-remaining-tokens', 'N/A')}")
            print(f"  Reset (req):       {headers.get('x-ratelimit-reset-requests', 'N/A')}")
            print(f"  Reset (tokens):    {headers.get('x-ratelimit-reset-tokens', 'N/A')}")
        raise HTTPException(status_code=429, detail="Rate limit reached. Please wait a moment and try again.")

    except Exception as e:
        print(f"Error during /ask: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred processing your request.")


@app.get("/health")
def health():
    return {"status": "ok"}