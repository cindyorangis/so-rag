import os
import fitz  # pymupdf
import ollama
from sentence_transformers import SentenceTransformer
from supabase import create_client
from dotenv import load_dotenv
import re

load_dotenv()

supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_PUBLISHABLE_KEY"])
storage_base = os.environ.get("SUPABASE_STORAGE_URL", "")
model = SentenceTransformer("BAAI/bge-base-en-v1.5")
ollama = ollama.Client()

HEADING_PATTERN = re.compile(r"^\d+(\.\d+)*\s+\w+")  # matches "3.3 Logging into PRIO"

def describe_image(image_bytes: bytes) -> str:
    try:
        response = ollama.chat(
            model="moondream",
            messages=[{
                "role": "user",
                "content": "Describe this screenshot briefly. What UI elements and actions are shown? Be concise, 1-2 sentences.",
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
    current_section = {"title": "Introduction", "content": "", "start_page": 1, "has_images": False}

    for page_num, page in enumerate(doc, start=1):
        blocks = page.get_text("dict")["blocks"]

        for block in blocks:
            if block["type"] == 0:  # text block
                for line in block["lines"]:
                    line_text = " ".join([s["text"] for s in line["spans"]]).strip()
                    if not line_text:
                        continue

                    # Detect section headings and start a new chunk
                    if HEADING_PATTERN.match(line_text) and len(line_text) < 80:
                        if current_section["content"].strip():
                            current_section["end_page"] = page_num - 1
                            sections.append(current_section)
                        current_section = {
                            "title": line_text,
                            "content": line_text + "\n",
                            "start_page": page_num,
                            "has_images": False
                        }
                    else:
                        current_section["content"] += line_text + "\n"

            elif block["type"] == 1:  # image block
                current_section["has_images"] = True
                try:
                    xref = block["image"]
                    base_image = doc.extract_image(xref)
                    description = describe_image(base_image["image"])
                    current_section["content"] += description + "\n"
                except Exception as e:
                    current_section["content"] += "[Screenshot]\n"

    # Append the last section
    if current_section["content"].strip():
        current_section["end_page"] = len(doc)
        sections.append(current_section)

    return sections

def ingest_procedure_pdf(pdf_path: str):
    filename = os.path.basename(pdf_path)
    print(f"Processing {filename}...")
    sections = extract_sections(pdf_path)
    print(f"  Found {len(sections)} sections")

    for section in sections:
        content = section["content"].strip()
        if len(content) < 50:
            continue

        embedding = model.encode(content).tolist()

        supabase.table("documents").insert({
            "content": content,
            "embedding": embedding,
            "source": filename,
            "page_number": section["start_page"],
            "section_title": section["title"],
            "chunk_type": "procedure",
            "pdf_url": f"{storage_base}/{filename}" if storage_base else None,
        }).execute()

    print(f"  Inserted {len(sections)} chunks")

if __name__ == "__main__":
    pdf_dir = "pdfs/procedures"  # separate folder from regular PDFs
    os.makedirs(pdf_dir, exist_ok=True)
    for fname in os.listdir(pdf_dir):
        if fname.endswith(".pdf"):
            ingest_procedure_pdf(os.path.join(pdf_dir, fname))
    print("Done.")