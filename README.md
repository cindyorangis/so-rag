# ServiceOntario Manual Search — README

---

## What This Is

A self-hosted RAG (Retrieval-Augmented Generation) tool that lets you ask plain English questions and get answers sourced directly from ServiceOntario PDF manuals. No internet search, no hallucinated answers — only what's in the manuals, with page citations.

---

# For Developers

## Tech Stack

| Layer | Tool |
|---|---|
| PDF Parsing | `pdfplumber` (Python) |
| Embeddings | `sentence-transformers` — `all-MiniLM-L6-v2` (local, free) |
| Vector Database | Supabase pgvector |
| LLM | Groq API — Llama 3.3 70B (free tier) |
| Backend | FastAPI (Python) |
| Frontend | Next.js + Tailwind CSS |

---

## Prerequisites

- Python 3.10+
- Node.js 18+
- A Supabase project
- A Groq API key (free at [console.groq.com](https://console.groq.com))

---

## Folder Structure

```
serviceontario-rag/
├── ingest/                  # Run once at home to load PDFs
│   ├── pdfs/                # Drop PDF manuals here (gitignored)
│   ├── ingest.py
│   ├── requirements.txt
│   └── .env
├── api/                     # FastAPI backend — deploy to Railway
│   ├── main.py
│   ├── requirements.txt
│   └── .env
├── web/                     # Next.js frontend — deploy to Vercel
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   └── manuals/
│   │       └── page.tsx
│   ├── package.json
│   └── .env.local
├── .gitignore
└── README.md
```

---

## Step 1 — Supabase Setup

In your Supabase project, go to the **SQL Editor** and run:

```sql
create extension if not exists vector;

create table documents (
  id bigserial primary key,
  content text not null,
  embedding vector(384),
  source text,
  page_number int
);

create or replace function match_documents(
  query_embedding vector(384),
  match_count int default 10
)
returns table(
  id bigint,
  content text,
  source text,
  page_number int,
  similarity float
)
language sql stable as $$
  select id, content, source, page_number,
    1 - (embedding <=> query_embedding) as similarity
  from documents
  order by embedding <=> query_embedding
  limit match_count;
$$;

create index on documents
  using ivfflat (embedding vector_cosine_ops)
  with (lists = 100);
```

---

## Step 2 — Ingest PDFs (run once, at home)

```bash
cd ingest
pip install -r requirements.txt
```

Create `ingest/.env`:
```
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_service_role_key
```

Drop all ServiceOntario PDF manuals into `ingest/pdfs/`, then run:

```bash
python ingest.py
```

This will take a while for large PDF sets — leave it running. Each PDF is parsed page by page, chunked, embedded locally, and stored in Supabase. You only ever need to run this again if you add new manuals.

---

## Step 3 — Run the API locally

```bash
cd api
pip install -r requirements.txt
```

Create `api/.env`:
```
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_service_role_key
GROQ_API_KEY=your_groq_api_key
```

Start the server:
```bash
uvicorn main:app --reload --port 8000
```

Test it:
```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What documents are required for a vehicle permit?"}'
```

---

## Step 4 — Run the Web App locally

```bash
cd web
npm install
```

Create `web/.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Update the fetch URL in `web/app/manuals/page.tsx` to use the env variable:
```ts
const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/ask`, { ... });
```

Start it:
```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

---

## Deploying

### API → Railway

1. Push `api/` to a GitHub repo (or the full monorepo)
2. Create a new project on [railway.app](https://railway.app)
3. Connect your repo, set root directory to `api/`
4. Add environment variables in Railway dashboard (same as `api/.env`)
5. Railway auto-detects Python — it will run `uvicorn main:app --host 0.0.0.0 --port $PORT`
6. Copy your Railway public URL

### Web → Vercel

1. Push `web/` to GitHub
2. Import project on [vercel.com](https://vercel.com)
3. Set root directory to `web/`
4. Add environment variable: `NEXT_PUBLIC_API_URL=https://your-railway-url.railway.app`
5. Deploy

---

## Adding New Manuals Later

1. Drop new PDFs into `ingest/pdfs/`
2. Run `python ingest.py` again from your home machine
3. New content is appended to Supabase — no redeployment needed

---

## Environment Variables Summary

| File | Variable | Where to get it |
|---|---|---|
| `ingest/.env` | `SUPABASE_URL` | Supabase → Project Settings → API |
| `ingest/.env` | `SUPABASE_KEY` | Supabase → Project Settings → API → service_role |
| `api/.env` | `SUPABASE_URL` | Same as above |
| `api/.env` | `SUPABASE_KEY` | Same as above |
| `api/.env` | `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) |
| `web/.env.local` | `NEXT_PUBLIC_API_URL` | Your Railway deployment URL (or `http://localhost:8000` locally) |

---

## .gitignore

Make sure these are never committed:
```
ingest/pdfs/
ingest/.env
api/.env
web/.env.local
__pycache__/
*.pyc
web/.next/
web/node_modules/
```

---

---

# For Users

## What This Tool Does

This tool lets you search through ServiceOntario manuals by asking plain questions in plain English. Instead of manually searching through hundreds of PDF pages, you type your question and get a direct answer — with references to which manual and page number the answer came from.

---

## How to Use It

1. Open the website
2. Type your question in the text box at the bottom — for example:
   - *"What documents do I need to register a vehicle?"*
   - *"How do I get a replacement driver's licence?"*
   - *"What are the fees for a personalized plate?"*
3. Press **Enter** or click **Ask**
4. Your answer will appear with citations showing which manual and page it came from

---

## Things to Know

- **Answers only come from the manuals.** If something isn't covered in the uploaded manuals, the tool will tell you it couldn't find an answer rather than guessing.
- **It is not connected to the internet.** It will not reflect recent policy changes unless the manuals have been updated and re-ingested.
- **Citations are shown below each answer.** You can use the page number to find the original passage in the source PDF if you need to verify something.
- **It is not an official ServiceOntario service.** Always confirm important information directly with ServiceOntario for anything official or time-sensitive.

---

## Troubleshooting

| Problem | What to do |
|---|---|
| "Something went wrong" error | The API server may be down — contact your administrator |
| Answer says it couldn't find anything | Try rephrasing your question, or the topic may not be covered in the loaded manuals |
| Answer seems outdated | The manuals may need to be updated — contact your administrator |