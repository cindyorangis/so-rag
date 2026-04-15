import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from supabase import create_client
from sentence_transformers import SentenceTransformer
from groq import Groq

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://so-rag.vercel.app", "https://cindyorangis.com"],
    allow_methods=["*"],
    allow_headers=["*"],
)

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_PUBLISHABLE_KEY"))
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
embedder = SentenceTransformer("all-MiniLM-L6-v2")


class AskRequest(BaseModel):
    question: str
    match_count: int = 10


class Source(BaseModel):
    source: str
    page_number: int


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]


@app.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest):
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    # 1. Embed the question
    query_embedding = embedder.encode(body.question).tolist()

    # 2. Retrieve relevant chunks from Supabase
    result = supabase.rpc("match_documents", {
        "query_embedding": query_embedding,
        "match_count": body.match_count,
    }).execute()

    if not result.data:
        return AskResponse(answer="I couldn't find anything relevant in the manuals.", sources=[])

    # 3. Build context from retrieved chunks
    chunks = result.data
    context = "\n\n---\n\n".join(
        f"[{c['source']} — p.{c['page_number']}]\n{c['content']}"
        for c in chunks
    )

    # 4. Ask Groq
    prompt = f"""You are a helpful assistant that answers questions strictly using the ServiceOntario manual excerpts below.
If the answer is not found in the excerpts, say so clearly — do not make anything up.

MANUAL EXCERPTS:
{context}

QUESTION:
{body.question}

ANSWER:"""

    completion = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,      # low temp = more factual
        max_tokens=1024,
    )

    answer = completion.choices[0].message.content.strip()

    # 5. Deduplicate sources
    seen = set()
    sources = []
    for c in chunks:
        key = (c["source"], c["page_number"])
        if key not in seen:
            seen.add(key)
            sources.append(Source(source=c["source"], page_number=c["page_number"]))

    return AskResponse(answer=answer, sources=sources)


@app.get("/health")
def health():
    return {"status": "ok"}