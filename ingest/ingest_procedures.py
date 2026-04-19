import os
import fitz  # pymupdf
import ollama as ollama_lib
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter
from supabase import create_client
from dotenv import load_dotenv
import re

load_dotenv()

supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_PUBLISHABLE_KEY"])
storage_base = os.environ.get("SUPABASE_STORAGE_URL", "")
model = SentenceTransformer("BAAI/bge-base-en-v1.5")
ollama = ollama_lib.Client()

HEADING_PATTERN = re.compile(r"^\d+(\.\d+)*\s+\w+")  # matches "3.3 Logging into PRIO"

# Procedure sections can be long — chunk them so nothing gets cut off by LLM context
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=150,
    separators=["\n\n", "\n", ". ", " ", ""]
)

def get_already_ingested() -> set[str]:
    """Fetch filenames already present in the DB to avoid re-ingesting."""
    res = supabase.table("documents").select("source").execute()
    return set(item["source"] for item in res.data)

def describe_image(image_bytes: bytes) -> str:
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
        return f"[Screenshot: {response['message']['content'].strip()}]"
    except Exception as e:
        print(f"  Image description failed: {e}")
        return "[Screenshot]"

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
        blocks = page.get_text("dict")["blocks"]

        for block in blocks:
            if block["type"] == 0:  # text block
                for line in block["lines"]:
                    line_text = " ".join([s["text"] for s in line["spans"]]).strip()
                    if not line_text:
                        continue

                    if HEADING_PATTERN.match(line_text) and len(line_text) < 80:
                        # Save the current section before starting a new one
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
                current_section["has_images"] = True
                try:
                    # pymupdf uses "xref" key, not "image", for the image reference
                    xref = block.get("xref") or block.get("image")
                    if xref:
                        base_image = doc.extract_image(xref)
                        description = describe_image(base_image["image"])
                        current_section["content"] += description + "\n"
                    else:
                        current_section["content"] += "[Screenshot]\n"
                except Exception as e:
                    print(f"  Image extraction failed on page {page_num}: {e}")
                    current_section["content"] += "[Screenshot]\n"

    # Append the last section
    if current_section["content"].strip():
        current_section["end_page"] = len(doc)
        sections.append(current_section)

    return sections

def ingest_procedure_pdf(pdf_path: str):
    filename = os.path.basename(pdf_path)
    print(f"\n--- Processing: {filename} ---")
    sections = extract_sections(pdf_path)
    print(f"  Found {len(sections)} sections")

    inserted = 0
    skipped = 0

    for section in sections:
        content = section["content"].strip()
        if len(content) < 50:
            skipped += 1
            continue

        # Chunk large sections so the LLM isn't fed an entire section as one blob
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

    print(f"  Inserted {inserted} chunks, skipped {skipped} short sections")

if __name__ == "__main__":
    pdf_dir = "pdfs/procedures"
    os.makedirs(pdf_dir, exist_ok=True)

    already_ingested = get_already_ingested()

    for fname in sorted(os.listdir(pdf_dir)):
        if not fname.endswith(".pdf"):
            continue
        if fname in already_ingested:
            print(f"Skipping {fname} (already ingested)")
            continue
        ingest_procedure_pdf(os.path.join(pdf_dir, fname))

    print("\nDone.")