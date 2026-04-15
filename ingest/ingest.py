import os
import pdfplumber
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client
from sentence_transformers import SentenceTransformer

load_dotenv()

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
model = SentenceTransformer("all-MiniLM-L6-v2")

CHUNK_SIZE = 500      # characters
CHUNK_OVERLAP = 50    # overlap between chunks to avoid cutting context

def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start += size - overlap
    return chunks

def ingest_pdf(pdf_path: Path):
    print(f"Processing {pdf_path.name}...")
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text()
            if not text or len(text.strip()) < 50:
                continue  # skip blank/header-only pages

            chunks = chunk_text(text)
            embeddings = model.encode(chunks).tolist()

            rows = [
                {
                    "content": chunk,
                    "embedding": embedding,
                    "source": pdf_path.name,
                    "page_number": page_num,
                }
                for chunk, embedding in zip(chunks, embeddings)
            ]

            supabase.table("documents").insert(rows).execute()
            print(f"  Page {page_num}/{len(pdf.pages)} — {len(chunks)} chunks")

if __name__ == "__main__":
    pdf_dir = Path("./pdfs")  # drop your PDFs in here
    for pdf_file in sorted(pdf_dir.glob("*.pdf")):
        ingest_pdf(pdf_file)
    print("Done!")