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

# Updated CORS to include common development and production origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Adjust to specific domains for production security
    allow_methods=["*"],
    allow_headers=["*"],
)

# Use Service Role Key for consistent backend access
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
embedder = SentenceTransformer("all-MiniLM-L6-v2")

class AskRequest(BaseModel):
    question: str
    match_count: int = 8 # Reduced slightly to ensure we stay within LLM context window

class Source(BaseModel):
    source: str
    page_number: int
    content: str

class AskResponse(BaseModel):
    answer: str
    sources: list[Source]

@app.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest):
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        # 1. Embed the question
        query_embedding = embedder.encode(body.question).tolist()

        # 2. Retrieve relevant chunks
        result = supabase.rpc("match_documents", {
            "query_embedding": query_embedding,
            "match_count": body.match_count,
        }).execute()

        if not result.data:
            return AskResponse(answer="I'm sorry, I couldn't find any information regarding that in the available ServiceOntario manuals.", sources=[])

        # 3. Build context with clear structure
        # We explicitly label the sources so the LLM can refer to them accurately
        context_blocks = []
        for i, c in enumerate(result.data):
            block = f"SOURCE {i+1} [{c['source']} — Page {c['page_number']}]:\n{c['content']}"
            context_blocks.append(block)
        
        context = "\n\n---\n\n".join(context_blocks)

        # 4. Ask Groq with a robust System Prompt
        # We use 'system' for rules and 'user' for the specific query
        system_prompt = (
            "You are a professional ServiceOntario Support Assistant. Your goal is to provide accurate "
            "information based ONLY on the provided manual excerpts. \n\n"
            "RULES:\n"
            "1. Only use the provided context. If the answer isn't there, say you don't know.\n"
            "2. Some data is in Markdown tables. Interpret columns and rows carefully to provide accurate fees or requirements.\n"
            "3. Use bullet points for lists of requirements or steps.\n"
            "4. Be concise but maintain a professional, helpful tone.\n"
            "5. Do NOT mention 'Source 1' or 'the context' in your final answer. Just provide the information."
        )

        user_prompt = f"CONTEXT:\n{context}\n\nQUESTION: {body.question}"

        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1, # Even lower temperature for maximum factual accuracy
            max_tokens=800,
        )

        answer = completion.choices[0].message.content.strip()

        # 5. Clean up and deduplicate sources for the UI
        seen_sources = set()
        unique_sources = []
        for c in result.data:
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