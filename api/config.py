import os
from dotenv import load_dotenv
from supabase import create_client
from sentence_transformers import SentenceTransformer, CrossEncoder
from groq import Groq

load_dotenv()

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_PUBLISHABLE_KEY"),
)

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

embedder = SentenceTransformer("BAAI/bge-base-en-v1.5")
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

ALLOWED_ORIGINS: list[str] = os.getenv("ALLOWED_ORIGINS", "").split(",")

# Ordered — first is primary, rest are fallbacks in sequence
GROQ_MODELS = [
    {
        "id": "llama-3.3-70b-versatile",
        "label": "Llama 3.3 70B",
        "description": "Best for complex policy questions",
        "tier": "primary",
    },
    {
        "id": "meta-llama/llama-4-scout-17b-16e-instruct",
        "label": "Llama 4 Scout 17Bx16E",
        "description": "Good for complex questions; fallback if 70B is rate limited",
        "tier": "secondary",
    },
    {
        "id": "llama-3.1-8b-instant",
        "label": "Llama 3.1 8B",
        "description": "Fastest; good for simple lookups",
        "tier": "fast",
    },
]

PRIMARY_MODEL_ID = GROQ_MODELS[0]["id"]