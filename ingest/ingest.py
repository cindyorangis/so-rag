import os
import pdfplumber
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

# Use Service Role Key for ingestion (bypass RLS)
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_PUBLISHABLE_KEY"))
model = SentenceTransformer("BAAI/bge-base-en-v1.5")

# Smarter Splitter: Tries to keep paragraphs and sentences together
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=150,
    separators=["\n\n", "\n", ". ", "! ", "? ", " ", ""]
)

def get_already_ingested():
    """Fetch list of unique filenames already in the DB."""
    res = supabase.table("documents").select("source").execute()
    return set(item['source'] for item in res.data)

def table_to_markdown(table):
    if not table: return ""
    cleaned = []
    for row in table:
        cleaned_row = []
        for cell in row:
            if cell:
                cell = cell.replace("\n", " ").strip()
                cell = " ".join(cell.split())
            cleaned_row.append(cell or "")
        cleaned.append(cleaned_row)
    rows = [" | ".join(cleaned_row) for cleaned_row in cleaned]
    if len(rows) > 1:
        header_sep = "|".join(["---"] * len(cleaned[0]))
        rows.insert(1, header_sep)
    return "\n".join(rows)

def detect_section_title(text: str) -> str | None:
    """Return the first likely heading found on the page, or None."""
    for line in text.split("\n"):
        line = line.strip()
        if 10 < len(line) < 80 and (line.isupper() or line.istitle()):
            return line
    return None

def extract_page_content(page):
    """
    Extract text and tables separately using bounding box exclusion
    so table content is never duplicated in the text extraction.

    pdfplumber's extract_text() includes table cells by default.
    We find table bounding boxes first, then extract only words that
    fall outside those regions — keeping prose and tables cleanly separated.
    """
    # Step 1: get bounding boxes for all tables on this page
    table_bboxes = [t.bbox for t in page.find_tables()]

    # Step 2: extract text from non-table regions only
    if table_bboxes:
        words = page.extract_words()
        non_table_words = []
        for word in words:
            inside_table = any(
                word["x0"] >= bbox[0] - 2 and
                word["x1"] <= bbox[2] + 2 and
                word["top"] >= bbox[1] - 2 and
                word["bottom"] <= bbox[3] + 2
                for bbox in table_bboxes
            )
            if not inside_table:
                non_table_words.append(word["text"])
        raw_text = " ".join(non_table_words)
    else:
        # No tables on this page — extract text normally, preserving layout
        raw_text = page.extract_text() or ""

    # Step 3: extract and format tables as markdown
    tables = page.extract_tables()
    table_md = "\n\n".join([table_to_markdown(t) for t in tables if t])

    return raw_text, table_md

def ingest_pdf(pdf_path: Path):
    print(f"--- Processing: {pdf_path.name} ---")

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):

            # Extract prose and tables without duplication
            raw_text, table_md = extract_page_content(page)

            # Combine: prose first, then table markdown
            parts = [p for p in [raw_text.strip(), table_md.strip()] if p]
            combined_content = "\n\n".join(parts)

            if len(combined_content) < 50:
                continue

            # Detect section title from raw prose text
            section_title = detect_section_title(raw_text)

            # Chunk and embed
            chunks = text_splitter.split_text(combined_content)
            embeddings = model.encode(chunks).tolist()

            rows = [
                {
                    "content": chunk,
                    "embedding": embedding,
                    "source": pdf_path.name,
                    "page_number": page_num,
                    "section_title": section_title,
                }
                for chunk, embedding in zip(chunks, embeddings)
            ]

            try:
                supabase.table("documents").insert(rows).execute()
                print(f"  Page {page_num}/{len(pdf.pages)}: {len(chunks)} chunks — section: {section_title or 'none detected'}")
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