import os
import fitz  # pymupdf
import ollama as ollama_lib
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter
from supabase import create_client
from dotenv import load_dotenv
import re
import httpx

load_dotenv()

supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_PUBLISHABLE_KEY"])
storage_base = os.environ.get("SUPABASE_STORAGE_URL", "")
model = SentenceTransformer("BAAI/bge-base-en-v1.5")
ollama = ollama_lib.Client(timeout=30)  # 30s timeout — moondream hangs without this

HEADING_PATTERN = re.compile(r"^\d+(\.\d+)*\s+\w+")  # matches "3.3 Logging into PRIO"

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=150,
    separators=["\n\n", "\n", ". ", " ", ""]
)

# ── Helpers ────────────────────────────────────────────────────────────────────

def get_already_ingested() -> set[str]:
    res = supabase.table("documents").select("source").execute()
    return set(item["source"] for item in res.data)

def check_ollama() -> bool:
    """Verify Ollama is running and moondream is available before starting."""
    try:
        models = ollama_lib.list()
        names = [m.model for m in models.models]
        available = any("moondream" in n for n in names)
        if not available:
            print(f"  WARNING: moondream not found. Available models: {names}")
            print(f"  Run: ollama pull moondream")
        return available
    except Exception as e:
        print(f"  ERROR: Cannot connect to Ollama — is it running? ({e})")
        print(f"  Run: ollama serve")
        return False

def describe_image(image_bytes: bytes, page_num: int, img_index: int) -> str:
    print(f"    Describing image {img_index} on page {page_num}...", flush=True)
    try:
        response = ollama.chat(
            model="moondream",
            messages=[{
                "role": "user",
                "content": (
                    "Describe this screenshot briefly. "
                    "What UI elements, buttons, fields, or actions are shown? "
                    "Be concise, 1-2 sentences."
                ),
                "images": [image_bytes]
            }]
        )
        desc = response["message"]["content"].strip()
        print(f"    Done: {desc[:60]}{'...' if len(desc) > 60 else ''}", flush=True)
        return f"[Screenshot: {desc}]"
    except httpx.TimeoutException:
        print(f"    Timed out on image {img_index} page {page_num} — skipping", flush=True)
        return "[Screenshot]"
    except Exception as e:
        print(f"    Image description failed: {e}", flush=True)
        return "[Screenshot]"

# ── Section extraction ─────────────────────────────────────────────────────────

def extract_sections(pdf_path: str) -> list[dict]:
    doc = fitz.open(pdf_path)
    sections = []
    current_section = {
        "title": "Introduction",
        "content": "",
        "start_page": 1,
        "has_images": False,
    }

    for page_num, page in enumerate(doc, start=1):
        print(f"  Scanning page {page_num}/{len(doc)}...", end="\r", flush=True)
        blocks = page.get_text("dict")["blocks"]
        img_index = 0

        for block in blocks:
            if block["type"] == 0:  # text block
                for line in block["lines"]:
                    line_text = " ".join([s["text"] for s in line["spans"]]).strip()
                    if not line_text:
                        continue

                    if HEADING_PATTERN.match(line_text) and len(line_text) < 80:
                        if current_section["content"].strip():
                            current_section["end_page"] = page_num - 1
                            sections.append(current_section)
                        current_section = {
                            "title": line_text,
                            "content": line_text + "\n",
                            "start_page": page_num,
                            "has_images": False,
                        }
                    else:
                        current_section["content"] += line_text + "\n"

            elif block["type"] == 1:  # image block
                img_index += 1
                current_section["has_images"] = True
                try:
                    image_bytes = None
                    xref = block.get("xref")

                    if isinstance(xref, int) and xref > 0:
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                    elif isinstance(block.get("image"), bytes):
                        image_bytes = block["image"]

                    if image_bytes:
                        description = describe_image(image_bytes, page_num, img_index)
                        current_section["content"] += description + "\n"
                    else:
                        current_section["content"] += "[Screenshot]\n"
                except Exception as e:
                    print(f"\n  Image extraction failed on page {page_num}: {e}", flush=True)
                    current_section["content"] += "[Screenshot]\n"

    print()  # newline after the \r progress line
    if current_section["content"].strip():
        current_section["end_page"] = len(doc)
        sections.append(current_section)

    return sections

# ── Ingestion ──────────────────────────────────────────────────────────────────

def ingest_procedure_pdf(pdf_path: str):
    filename = os.path.basename(pdf_path)
    print(f"\n--- Processing: {filename} ---")
    sections = extract_sections(pdf_path)
    print(f"  Found {len(sections)} sections — embedding and inserting...")

    inserted = 0
    skipped = 0

    for i, section in enumerate(sections, start=1):
        content = section["content"].strip()
        if len(content) < 50:
            skipped += 1
            continue

        print(f"  [{i}/{len(sections)}] '{section['title'][:50]}'", flush=True)

        chunks = text_splitter.split_text(content)
        embeddings = model.encode(chunks).tolist()

        rows = [
            {
                "content": chunk,
                "embedding": embedding,
                "source": filename,
                "page_number": section["start_page"],
                "section_title": section["title"],
                "chunk_type": "procedure",
                "pdf_url": f"{storage_base}/{filename}" if storage_base else None,
            }
            for chunk, embedding in zip(chunks, embeddings)
        ]

        try:
            supabase.table("documents").insert(rows).execute()
            inserted += len(rows)
        except Exception as e:
            print(f"  Insert error for section '{section['title']}': {e}")

    print(f"  Done — inserted {inserted} chunks, skipped {skipped} short sections")

# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pdf_dir = "pdfs/procedures"
    os.makedirs(pdf_dir, exist_ok=True)

    print("Checking Ollama...")
    ollama_ok = check_ollama()
    if not ollama_ok:
        print("Aborting — fix Ollama first, then re-run.")
        exit(1)

    already_ingested = get_already_ingested()

    for fname in sorted(os.listdir(pdf_dir)):
        if not fname.endswith(".pdf"):
            continue
        if fname in already_ingested:
            print(f"Skipping {fname} (already ingested)")
            continue
        ingest_procedure_pdf(os.path.join(pdf_dir, fname))

    print("\nDone.")