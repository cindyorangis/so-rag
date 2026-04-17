import os
import hashlib
import pdfplumber
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

# Use Service Role Key for ingestion (bypass RLS)
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_PUBLISHABLE_KEY"))
model = SentenceTransformer("all-MiniLM-L6-v2")

# 1. Smarter Splitter: Tries to keep paragraphs and sentences together
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=600,
    chunk_overlap=80,
    separators=["\n\n", "\n", ". ", " ", ""]
)

def get_already_ingested():
    """Fetch list of unique filenames already in the DB."""
    res = supabase.table("documents").select("source").execute()
    return set(item['source'] for item in res.data)

def table_to_markdown(table):
    """Converts a list-of-lists table into a Markdown string."""
    if not table: return ""
    # Filter out None values and join with pipes
    rows = [" | ".join([str(cell) if cell else "" for cell in row]) for row in table]
    if len(rows) > 1:
        # Add the header separator line
        header_sep = "|".join(["---"] * len(table[0]))
        rows.insert(1, header_sep)
    return "\n".join(rows)

def ingest_pdf(pdf_path: Path):
    print(f"--- Processing: {pdf_path.name} ---")
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            # 2. Extract both text and tables
            raw_text = page.extract_text() or ""
            
            # Extract tables and format as Markdown
            tables = page.extract_tables()
            table_md = "\n\n".join([table_to_markdown(t) for t in tables])
            
            # Combine text and table data for this page
            combined_content = f"{raw_text}\n\n{table_md}".strip()
            
            if len(combined_content) < 50:
                continue

            # 3. Chunk the combined content
            chunks = text_splitter.split_text(combined_content)
            
            # 4. Generate Embeddings in a batch for the page
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

            # Insert all chunks for the page at once
            try:
                supabase.table("documents").insert(rows).execute()
                print(f"  Page {page_num}/{len(pdf.pages)}: Ingested {len(chunks)} chunks")
            except Exception as e:
                print(f"  Error on Page {page_num}: {e}")

if __name__ == "__main__":
    pdf_dir = Path("./pdfs")
    ingested_files = get_already_ingested()
    
    for pdf_file in sorted(pdf_dir.glob("*.pdf")):
        if pdf_file.name in ingested_files:
            print(f"Skipping {pdf_file.name} (already ingested)")
            continue
            
        ingest_pdf(pdf_file)
    
    print("Ingestion complete.")