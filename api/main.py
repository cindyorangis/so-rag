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

origins = os.getenv("ALLOWED_ORIGINS", "").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_PUBLISHABLE_KEY"))
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
embedder = SentenceTransformer("BAAI/bge-base-en-v1.5")
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

GROQ_MODELS = [
    {
        "id": "llama-3.3-70b-versatile",
        "label": "Llama 3.3 70B",
        "description": "Best for complex policy questions",
        "tier": "primary",
    },
    {
        "id": "llama-3.1-8b-instant",
        "label": "Llama 3.1 8B",
        "description": "Faster, good for simple lookups",
        "tier": "fast",
    },
    {
        "id": "gemma2-9b-it",
        "label": "Gemma 2 9B",
        "description": "Fallback when others are unavailable",
        "tier": "fallback",
    },
]

class AskRequest(BaseModel):
    question: str
    match_count: int = 12  # wider pool for reranker to work with
    model_id: str | None = None # if None, use fallback chain

class Source(BaseModel):
    source: str
    page_number: int
    content: str
    section_title: str | None = None
    pdf_url: str | None = None

class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    mode: str = "answer"

class FeedbackRequest(BaseModel):
    question: str
    answer: str
    rating: str  # "up" or "down"
    sources: list[dict] = []
    model_used: str | None = None

def sanitize_question(q: str) -> str:
    q = q.strip()
    if not q:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    if len(q) > 500:
        raise HTTPException(status_code=400, detail="Question is too long (max 500 characters).")
    return q

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
            .select("id, content, source, page_number, chunk_type, section_title, pdf_url") \
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
        if count < 3:  # max 3 chunks per source
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

@app.get("/models")
async def get_models():
    """
    Probe each model with a minimal request to check rate limit headers.
    Returns availability and reset time for each.
    """
    statuses = []
    for m in GROQ_MODELS:
        try:
            resp = groq_client.chat.completions.with_raw_response.create(
                model=m["id"],
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
            )
            headers = resp.headers
            statuses.append({
                **m,
                "available": True,
                "reset_in": None,
                "remaining_requests": headers.get("x-ratelimit-remaining-requests"),
                "remaining_tokens": headers.get("x-ratelimit-remaining-tokens"),
            })
        except RateLimitError as e:
            reset = None
            if hasattr(e, 'response') and e.response is not None:
                reset = e.response.headers.get("x-ratelimit-reset-requests")
            statuses.append({
                **m,
                "available": False,
                "reset_in": reset,  # e.g. "47s"
                "remaining_requests": "0",
                "remaining_tokens": "0",
            })
        except Exception:
            statuses.append({
                **m,
                "available": True,  # assume available if we can't check
                "reset_in": None,
                "remaining_requests": None,
                "remaining_tokens": None,
            })
    return {"models": statuses}

@app.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest):
    question = sanitize_question(body.question)
 
    try:
        supabase.table("queries").insert({
            "question": question,
            "model_used": body.model_id or "llama-3.3-70b-versatile",
        }).execute()
    except Exception as e:
        print(f"Query log error: {e}")
 
    try:
        # 1. Embed the question (BGE prefix for retrieval)
        query_embedding = embedder.encode(
            f"Represent this sentence for searching relevant passages: {question}"
        ).tolist()
 
        # 2. Hybrid search — semantic + keyword, deduplicated
        candidates = await hybrid_search(question, query_embedding, body.match_count)
 
        if not candidates:
            return AskResponse(
                answer="I'm sorry, I couldn't find any information regarding that in the available ServiceOntario manuals.",
                sources=[]
            )
 
        # 3. Rerank candidates, keep top 8 for the LLM
        reranked = rerank(question, candidates, top_k=8)
 
        # 4. Build context from reranked chunks
        context_blocks = []
        for i, c in enumerate(reranked):
            block = f"SOURCE {i+1} [{c['source']} — Page {c['page_number']}]:\n{c['content']}"
            context_blocks.append(block)
 
        context = "\n\n---\n\n".join(context_blocks)
 
        # 5. Build system prompt based on content type
        is_procedure = any(c.get("chunk_type") == "procedure" for c in reranked)
 
        if is_procedure:
            system_prompt = (
                "You are a professional ServiceOntario Support Assistant helping an agent at a service counter. "
                "The context contains step-by-step procedure instructions.\n\n"
                "FORMATTING:\n"
                "- You MUST format every step as a numbered list: 1. 2. 3. etc.\n"
                "- NEVER use plain sentences or bullet points (- or •) for steps — always numbers.\n"
                "- Each numbered item should be one clear action.\n"
                "- Each step should be a single clear action\n"
                "- Use **bold** for UI element names (button labels, field names, menu items)\n"
                "- If a step has sub-steps, indent them with two spaces\n\n"
                "RULES:\n"
                "1. Only include steps that appear in the provided context — do not invent steps.\n"
                "2. If screenshots are described in the context (marked [Screenshot: ...]), reference what they show if relevant.\n"
                "3. Do not include source labels or inline citations in your answer. Sources are displayed separately by the UI.\n"
                "4. If the context doesn't cover the full procedure, say so at the end."
            )
        else:
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
                "5. Tables contain fees and eligibility — read the column headers carefully before extracting values.\n"
                "6. Use bullet points for multi-step processes or lists of requirements.\n"
                "7. If multiple sources conflict, note the discrepancy and cite both.\n"
                "8. Never invent fees, form numbers, or deadlines.\n"
                "9. Do not include source labels or inline citations in your answer. Sources are displayed separately by the UI."
            )
 
        user_prompt = f"CONTEXT:\n{context}\n\nQUESTION: {question}"
 
        # 6. Build model chain — preferred model first, then fallbacks
        preferred = body.model_id
        if preferred and any(m["id"] == preferred for m in GROQ_MODELS):
            ordered_models = [preferred] + [m["id"] for m in GROQ_MODELS if m["id"] != preferred]
        else:
            ordered_models = [m["id"] for m in GROQ_MODELS]
 
        # 7. Try each model in order, falling back on rate limit
        completion = None
        used_model = None
        last_reset = None
 
        for model_name in ordered_models:
            try:
                completion = groq_client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.1,
                    max_tokens=1500,
                )
                used_model = model_name
                break
            except RateLimitError as e:
                reset = None
                if hasattr(e, 'response') and e.response is not None:
                    reset = e.response.headers.get('x-ratelimit-reset-requests')
                last_reset = reset
                print(f"Rate limit hit on {model_name}, trying next... (reset in {reset or 'unknown'})")
                continue
 
        # 8. All models exhausted
        if completion is None:
            wait_msg = f"Please try again in {last_reset}." if last_reset else "Please wait a moment and try again."
            raise HTTPException(
                status_code=429,
                detail=f"All models are currently rate limited. {wait_msg}"
            )
 
        if used_model != ordered_models[0]:
            print(f"Used fallback model: {used_model} (preferred was rate limited)")
 
        answer = completion.choices[0].message.content.strip()
 
        # 9. Deduplicate sources from reranked chunks for the UI
        seen_sources = set()
        unique_sources = []
        for c in reranked:
            source_id = f"{c['source']}-{c['page_number']}"
            if source_id not in seen_sources:
                seen_sources.add(source_id)
                unique_sources.append(Source(
                    source=c["source"],
                    page_number=c["page_number"],
                    content=c["content"],
                    section_title=c.get("section_title"),
                    pdf_url=c.get("pdf_url"),
                ))
 
        return AskResponse(
            answer=answer,
            sources=unique_sources,
            mode="procedure" if is_procedure else "answer"
        )
 
    except HTTPException:
        raise  # re-raise 429s and other HTTP exceptions cleanly
 
    except Exception as e:
        print(f"Error during /ask: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred processing your request.")

@app.post("/feedback")
async def feedback(body: FeedbackRequest):
    if body.rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="Rating must be 'up' or 'down'")
    try:
        supabase.table("feedback").insert({
            "question": body.question,
            "answer": body.answer,
            "rating": body.rating,
            "sources": body.sources,
            "model_used": body.model_used,
        }).execute()
        return {"ok": True}
    except Exception as e:
        print(f"Feedback error: {e}")
        raise HTTPException(status_code=500, detail="Failed to save feedback")
    
@app.get("/suggestions")
async def suggestions():
    try:
        result = supabase.rpc("top_suggestions", {"lim": 6}).execute()
        top = [q["question"].capitalize() for q in result.data]
        return {"suggestions": top}

    except Exception as e:
        print(f"Suggestions error: {e}")
        return {"suggestions": []}

@app.get("/health")
def health():
    return {"status": "ok"}