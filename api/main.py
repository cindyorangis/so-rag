from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from groq import RateLimitError

from config import ALLOWED_ORIGINS, GROQ_MODELS, PRIMARY_MODEL_ID, groq_client, supabase
from models import AskRequest, AskResponse, FeedbackRequest, Source
from prompts import get_system_prompt
from search import (
    build_context,
    embed_question,
    hybrid_search,
    rerank_chunks,
    sanitize_question,
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# /models
# ---------------------------------------------------------------------------

@app.get("/models")
async def get_models():
    """Probe each model with a minimal request to check rate limit headers."""
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
            if hasattr(e, "response") and e.response is not None:
                reset = e.response.headers.get("x-ratelimit-reset-requests")
            statuses.append({
                **m,
                "available": False,
                "reset_in": reset,
                "remaining_requests": "0",
                "remaining_tokens": "0",
            })
        except Exception:
            statuses.append({
                **m,
                "available": True,  # assume available if probe fails for non-rate-limit reason
                "reset_in": None,
                "remaining_requests": None,
                "remaining_tokens": None,
            })
    return {"models": statuses}


# ---------------------------------------------------------------------------
# /ask
# ---------------------------------------------------------------------------

@app.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest):
    question = sanitize_question(body.question)

    try:
        supabase.table("queries").insert({
            "question": question,
            "model_used": body.model_id or PRIMARY_MODEL_ID,
        }).execute()
    except Exception as e:
        print(f"Query log error: {e}")

    try:
        # 1. Embed
        query_embedding = embed_question(question)

        # 2. Hybrid search — semantic + keyword, deduplicated
        candidates = await hybrid_search(question, query_embedding, body.match_count)

        if not candidates:
            return AskResponse(
                answer="I'm sorry, I couldn't find any information regarding that in the available ServiceOntario manuals.",
                sources=[],
            )

        # 3. Rerank — keep top 8 for the LLM
        reranked = rerank_chunks(question, candidates, top_k=8)

        # 4. Build context + system prompt
        context = build_context(reranked)
        is_procedure = any(c.get("chunk_type") == "procedure" for c in reranked)
        system_prompt = get_system_prompt(is_procedure)
        user_prompt = f"CONTEXT:\n{context}\n\nQUESTION: {question}"

        # 5. Build model chain — preferred first, then fallbacks in registry order
        preferred = body.model_id
        if preferred and any(m["id"] == preferred for m in GROQ_MODELS):
            ordered_models = [preferred] + [m["id"] for m in GROQ_MODELS if m["id"] != preferred]
        else:
            ordered_models = [m["id"] for m in GROQ_MODELS]

        # 6. Try each model, falling back on rate limit
        completion = None
        used_model = None
        last_reset = None

        for model_id in ordered_models:
            try:
                completion = groq_client.chat.completions.create(
                    model=model_id,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.1,
                    max_tokens=1500,
                )
                used_model = model_id
                break
            except RateLimitError as e:
                reset = None
                if hasattr(e, "response") and e.response is not None:
                    reset = e.response.headers.get("x-ratelimit-reset-requests")
                last_reset = reset
                print(f"Rate limit on {model_id}, trying next... (reset in {reset or 'unknown'})")

        if completion is None:
            wait_msg = f"Please try again in {last_reset}." if last_reset else "Please wait a moment and try again."
            raise HTTPException(
                status_code=429,
                detail=f"All models are currently rate limited. {wait_msg}",
            )

        if used_model != ordered_models[0]:
            print(f"Used fallback model: {used_model}")

        answer = completion.choices[0].message.content.strip()

        # 7. Deduplicate sources for the UI
        seen_sources: set[str] = set()
        unique_sources: list[Source] = []
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
            mode="procedure" if is_procedure else "answer",
        )

    except HTTPException:
        raise

    except Exception as e:
        print(f"Error during /ask: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred processing your request.")


# ---------------------------------------------------------------------------
# /feedback
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# /suggestions
# ---------------------------------------------------------------------------

@app.get("/suggestions")
async def suggestions():
    try:
        result = supabase.rpc("top_suggestions", {"lim": 6}).execute()
        top = [q["question"].capitalize() for q in result.data]
        return {"suggestions": top}
    except Exception as e:
        print(f"Suggestions error: {e}")
        return {"suggestions": []}


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}