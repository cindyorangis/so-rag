# ServiceOntario Manual Search — README

---

## What This Is

A self-hosted RAG (Retrieval-Augmented Generation) tool that lets you ask plain English questions and get answers sourced directly from ServiceOntario PDF manuals. No internet search, no hallucinated answers — only what's in the manuals, with page citations.

Supports two document types:
- **Policy manuals** — returns direct answers with citations
- **Procedure manuals** — returns step-by-step instructions, with screenshots described automatically

---

# For Developers

## Tech Stack

| Layer | Tool |
|---|---|
| PDF Parsing | `pdfplumber` (policy docs), `pymupdf` (procedure manuals) |
| Image Description | Ollama — `moondream` (local, free) |
| Embeddings | `sentence-transformers` — `BAAI/bge-base-en-v1.5` (local, free) |
| Vector Database | Supabase pgvector |
| PDF Storage | Supabase Storage |
| LLM | Groq API — Llama 3.3 70B (free tier) |
| Backend | FastAPI (Python) |
| Frontend | Next.js + Tailwind CSS |

---

## Prerequisites

- Python 3.10+
- Node.js 18+
- A Supabase project
- A Groq API key (free at [console.groq.com](https://console.groq.com))
- Ollama (for procedure manual ingestion with screenshots)

---

## Folder Structure

```
serviceontario-rag/
├── ingest/                      # Run once at home to load PDFs
│   ├── pdfs/                    # Drop policy PDFs here (gitignored)
│   │   └── procedures/          # Drop procedure manuals here (gitignored)
│   ├── ingest.py                # For policy/FAQ docs
│   ├── ingest_procedures.py     # For step-by-step procedure manuals
│   ├── requirements.txt
│   └── .env
├── api/                         # FastAPI backend — deploy to Railway
│   ├── main.py
│   ├── requirements.txt
│   └── .env
├── web/                         # Next.js frontend — deploy to Vercel
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   └── manuals/
│   │       └── page.tsx
│   ├── components/
│   │   ├── ChatMessage.tsx
│   │   └── SourceCard.tsx
│   ├── types/
│   │   └── manuals.ts
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
  embedding vector(768),
  source text,
  page_number int,
  chunk_type text default 'text',
  section_title text,
  pdf_url text
);

create or replace function match_documents(
  query_embedding vector(768),
  match_count int default 12
)
returns table(
  id bigint,
  content text,
  source text,
  page_number int,
  chunk_type text,
  section_title text,
  pdf_url text,
  similarity float
)
language sql stable as $$
  select id, content, source, page_number, chunk_type, section_title, pdf_url,
    1 - (embedding <=> query_embedding) as similarity
  from documents
  where 1 - (embedding <=> query_embedding) > 0.35
  order by embedding <=> query_embedding
  limit match_count;
$$;

create index on documents
  using ivfflat (embedding vector_cosine_ops)
  with (lists = 100);
```

Run this to speed up keyword searches:

```sql
alter table documents add column fts tsvector
generated always as (to_tsvector('english', content)) stored;

create index documents_fts_idx on documents using gin (fts);
```

Create the feedback and queries tables (no RLS required — writes go through your service_role backend):

```sql
create table feedback (
  id bigserial primary key,
  question text not null,
  answer text not null,
  rating text not null check (rating in ('up', 'down')),
  sources jsonb,
  created_at timestamptz default now()
);

create table queries (
  id bigserial primary key,
  question text not null,
  created_at timestamptz default now()
);
```

Create the suggestions function (moves aggregation to SQL instead of fetching all rows into Python):

```sql
create or replace function top_suggestions(lim int default 6)
returns table(question text) language sql stable as $$
  select lower(trim(question)) as question
  from queries
  group by lower(trim(question))
  order by count(*) desc
  limit lim;
$$;
```

### Supabase Storage

1. Go to **Storage** → **New bucket**
2. Name it `manuals`
3. Set it to **Public**
4. Upload all your procedure PDFs (same files you ingested)

### If migrating from an existing setup

```sql
alter table documents add column if not exists chunk_type text default 'text';
alter table documents add column if not exists section_title text;
alter table documents add column if not exists pdf_url text;
```

Then replace the `match_documents` function using the definition above and re-run the ingest scripts.

---

## Step 2 — Ingest PDFs (run once, at home)

```bash
cd ingest
pip install -r requirements.txt
```

Create `ingest/.env`:
```
SUPABASE_URL=your_supabase_project_url
SUPABASE_PUBLISHABLE_KEY=your_supabase_publishable_key
SUPABASE_STORAGE_URL=https://your-project-ref.supabase.co/storage/v1/object/public/manuals
```

Your `SUPABASE_STORAGE_URL` is found in Supabase → Storage → select the `manuals` bucket → click any file → copy the URL up to and including `/manuals`.

> **Note:** The service role key bypasses Row Level Security. Never expose it in the browser or commit it to version control.

### Policy / FAQ docs

Drop PDFs into `ingest/pdfs/`, then run:

```bash
python ingest.py
```

Both scripts skip files already present in the database — safe to re-run if interrupted.

### Procedure manuals (with screenshots)

Procedure manuals like the IRP manual are chunked by section heading and have their screenshots automatically described using a local vision model. A public URL is stored with each chunk so users can open the source PDF directly to the cited page.

**First, install and start Ollama:**

```bash
brew install ollama
ollama pull moondream
ollama serve
```

Drop procedure PDFs into `ingest/pdfs/procedures/`, then in a separate terminal run:

```bash
python ingest_procedures.py
```

This will take a while for large manuals — leave it running. Ollama must be running in the background during ingest, but is not needed after that.

Both scripts append to the same `documents` table in Supabase. You only need to re-run them if you add or update manuals.

---

## Step 3 — Run the API locally

```bash
cd api
pip install -r requirements.txt
```

Create `api/.env`:
```
SUPABASE_URL=your_supabase_project_url
SUPABASE_PUBLISHABLE_KEY=your_supabase_publishable_key
GROQ_API_KEY=your_groq_api_key
ALLOWED_ORIGINS=http://localhost:3000,https://your_production.url
```

Start the server:
```bash
uvicorn main:app --reload --port 8080
```

Test it:
```bash
curl -X POST http://localhost:8080/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "How do I log into PRIO?"}'
```

---

## Step 4 — Run the Web App locally

```bash
cd web
npm install
```

Create `web/.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8080
```

Start it:
```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

---

## How Procedure Mode Works

When a query matches a procedure manual chunk, the API automatically switches to procedure mode:

- The response is formatted as numbered steps
- Screenshot descriptions (generated at ingest time) are included as context for the LLM
- The `mode: "procedure"` field is returned in the API response
- Citations include the section title and page number
- An **Open** link appears on each source card — clicking it opens the PDF directly to the cited page in a new tab

This detection is automatic — the same search bar handles both policy questions and procedure lookups.

---

## Answer Feedback

Every assistant response shows a Yes / No prompt. Ratings are written to the `feedback` table in Supabase with the full question, answer, sources, and timestamp.

To review feedback and identify answers that need improvement:

```sql
-- Most recent thumbs down
select question, created_at
from feedback
where rating = 'down'
order by created_at desc
limit 20;

-- Overall rating counts
select rating, count(*) from feedback group by rating;
```

---

## Query Suggestions

Every question asked is logged to the `queries` table. The `/suggestions` endpoint calls the `top_suggestions` SQL function to return the top 6 most common questions, which the frontend displays as suggestion chips.

Fallback suggestions are shown on fresh deploys until enough real queries have been logged.

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

For policy docs:
1. Drop new PDFs into `ingest/pdfs/`
2. Run `python ingest.py`

For procedure manuals:
1. Upload the new PDF to Supabase Storage → `manuals` bucket
2. Drop the same PDF into `ingest/pdfs/procedures/`
3. Start Ollama: `ollama serve`
4. Run `python ingest_procedures.py`

New content is appended to Supabase — no redeployment needed.

---

## Environment Variables Summary

| File | Variable | Where to get it |
|---|---|---|
| `ingest/.env` | `SUPABASE_URL` | Supabase → Project Settings → API |
| `ingest/.env` | `SUPABASE_PUBLISHABLE_KEY` | Supabase → Project Settings → API → service_role |
| `ingest/.env` | `SUPABASE_STORAGE_URL` | Supabase → Storage → manuals bucket → any file URL, trimmed to `/manuals` |
| `api/.env` | `SUPABASE_URL` | Same as above |
| `api/.env` | `SUPABASE_PUBLISHABLE_KEY` | Same as above |
| `api/.env` | `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) |
| `api/.env` | `ALLOWED_ORIGINS` | Comma-separated list of allowed frontend URLs |
| `web/.env.local` | `NEXT_PUBLIC_API_URL` | Your Railway deployment URL (or `http://localhost:8080` locally) |

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

## Routine Maintenance

Run these periodically in the Supabase SQL Editor to keep the data clean and useful.

### Monthly — review negative feedback

```sql
-- Questions that got thumbs down — investigate and improve retrieval or prompts
select question, created_at
from feedback
where rating = 'down'
order by created_at desc;
```

### Monthly — clean up test queries from suggestions

Queries logged during development will pollute the suggestions. Remove them before going live and periodically after:

```sql
-- Remove obvious test entries
delete from queries
where question ilike '%test%'
   or question ilike '%hello%'
   or question ilike '%asdf%'
   or length(trim(question)) < 10;
```

### Quarterly — review top queries vs manual coverage

```sql
-- Most asked questions — check if answers are good, or if manuals need updating
select question, count(*) as total
from queries
group by question
order by total desc
limit 20;
```

### Quarterly — trim old query logs

The `queries` table grows indefinitely. Keep the last 90 days for suggestions, archive or delete the rest:

```sql
delete from queries
where created_at < now() - interval '90 days';
```

### When manuals are updated

1. Delete documents for that source only:
```sql
delete from documents where source = 'IRP-Procedure-Manual-2025-Revision-A.pdf';
```
2. Re-upload the new PDF to Supabase Storage (replace the existing file)
3. Re-run the appropriate ingest script

Do not truncate the entire `documents` table unless re-ingesting everything — other manuals will stop working until they are re-ingested.

---

# For Users

## What This Tool Does

This tool lets you search through ServiceOntario manuals by asking plain questions in plain English. Instead of manually searching through hundreds of PDF pages, you type your question and get a direct answer — with references to which manual and page number the answer came from.

For procedure questions (like how to use PRIO or complete a specific workflow), answers are returned as step-by-step instructions.

---

## How to Use It

1. Open the website
2. Type your question in the text box at the bottom — for example:
   - *"What documents do I need to register a vehicle?"*
   - *"How do I log into PRIO?"*
   - *"How do I create an IRP supplement?"*
   - *"What are the fees for a personalized plate?"*
3. Press **Enter** or click **Ask**
4. Your answer will appear — either as a direct answer or as numbered steps, depending on the question
5. References below the answer show which manual, section, and page the answer came from
6. Click **Open** on any reference card to open the original PDF directly to the cited page
7. Use the **Yes** / **No** buttons to rate whether the answer was helpful

---

## Things to Know

- **Answers only come from the manuals.** If something isn't covered in the uploaded manuals, the tool will say so rather than guessing.
- **It is not connected to the internet.** It will not reflect recent policy changes unless the manuals have been updated and re-ingested.
- **References are shown below each answer.** Click **Open** to view the original page in the source PDF, including any screenshots.
- **Your feedback helps improve the tool.** Negative ratings are reviewed to identify and fix answers that need improvement.
- **It is not an official ServiceOntario service.** Always confirm important information directly with ServiceOntario for anything official or time-sensitive.

---

## Troubleshooting

| Problem | What to do |
|---|---|
| "Something went wrong" error | The API server may be down — contact your administrator |
| Answer says it couldn't find anything | Try rephrasing your question, or the topic may not be covered in the loaded manuals |
| Answer seems outdated | The manuals may need to be updated — contact your administrator |
| Open link not appearing on a reference | That document may not be uploaded to Supabase Storage yet — contact your administrator |
| Open link opens to wrong page | PDF page numbering may differ from manual page numbering — navigate manually from the cited page number |