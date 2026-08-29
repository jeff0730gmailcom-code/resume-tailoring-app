# Resume Tailor AI

An MVP app that tailors a user's master CV to a specific job description
using the OpenAI API, renders it into a hand-picked resume template, and
lets them download the result as a PDF or DOCX.

## Main user flow

1. User opens the website
2. Uploads a master CV (PDF/DOC/DOCX) — content only, its layout is not preserved
3. Pastes a job description and picks a resume template from the gallery
4. Clicks "Generate Tailored Resume"
5. Backend extracts CV text/structure and the AI tailors the content to the JD
6. User previews the generated resume
7. User downloads the result as a PDF or DOCX, rendered in the chosen template

## Status

The full main user flow is implemented end-to-end:

- Upload a PDF/DOC/DOCX CV → backend extracts text (`pypdf` / `python-docx`)
  and structures it into contact/summary/skills/experience/education
- Paste a job description and pick a template → AI (OpenAI) tailors the
  content, then it's rendered into that template
- Preview the tailored resume in the browser
- Download the tailored resume as a PDF (Jinja2 + Playwright) or DOCX
  (converted from that PDF via Word COM)

You need a valid `OPENAI_API_KEY` in `backend/.env` for the "Generate
Tailored Resume" step to work — upload/extraction and template rendering
work without one.

## Tech stack

- **Frontend:** React, TypeScript, Vite, Tailwind CSS
- **Backend:** Python, FastAPI
- **AI:** OpenAI API
- **Database:** SQLite (`backend/data/app.db`, via SQLAlchemy) — stores the
  resume template gallery and resume-generation history. No user
  authentication yet; the schema is auth-ready (`ResumeRecord.user_id`) but
  unused.
- **Rendering:** Jinja2 (HTML templates) + Playwright (headless Chromium,
  HTML → PDF) + Word COM (PDF → DOCX, Windows-only)

## Project structure

```
.
├── backend/
│   ├── app/
│   │   ├── api/routes/          # FastAPI route handlers (resume.py)
│   │   ├── core/                # Settings/config, fixed constants
│   │   ├── db/                  # SQLAlchemy models + session (SQLite)
│   │   ├── models/               # Pydantic schemas
│   │   ├── prompts/              # AI prompt text
│   │   ├── services/             # CV parsing, AI tailoring, template rendering
│   │   ├── templates/resumes/    # One folder per template: template.html.jinja2 + reference.pdf
│   │   ├── utils/                # Temp file helpers, perf timing
│   │   └── main.py               # FastAPI app entrypoint
│   ├── data/                 # SQLite database file (gitignored)
│   ├── static/                # Generated template thumbnails (gitignored)
│   ├── temp/                  # Temporary file storage (gitignored)
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/        # CvUpload, TemplateGallery, JobDescriptionInput, ResumePreview
│   │   ├── services/          # API client
│   │   ├── types/             # Shared TS types
│   │   └── App.tsx
│   ├── package.json
│   └── .env.example
└── README.md
```

## Prerequisites

- Node.js 18+ and npm
- Python 3.10+
- An OpenAI API key
- (Windows only, for DOCX downloads) Microsoft Word installed

## Backend setup

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt

# One-time: installs the headless Chromium browser Playwright uses to
# render resume templates to PDF.
playwright install chromium

copy .env.example .env   # Windows
# cp .env.example .env   # macOS/Linux
# then edit .env and set OPENAI_API_KEY

uvicorn app.main:app --reload
```

On startup the backend automatically creates `backend/data/app.db` (SQLite)
and seeds the resume templates from `backend/app/templates/resumes/` —
no manual database setup needed.

The API will be available at `http://localhost:8000`. Check `http://localhost:8000/health`.

## Frontend setup

```bash
cd frontend
npm install

copy .env.example .env   # Windows
# cp .env.example .env   # macOS/Linux

npm run dev
```

The app will be available at `http://localhost:5173`. On load, it pings the
backend `/health` endpoint and shows an "API: online/offline" badge in the
header.

After `npm run build` in `frontend/`, the backend also serves the app at
the uvicorn URL (for example `http://localhost:8090`) so one public address
can host both the UI and the API.

## Deploy online (Railway)

This project is set up for **[Railway](https://railway.com)** — one Docker
service that serves both the React UI and the FastAPI API.

Railway is the right host for this app as it grows past MVP: GitHub
auto-deploy, enough RAM for Playwright PDF rendering, a public HTTPS URL,
and a one-click PostgreSQL add-on when you add accounts/history later.

Hosting is cheap (~$5/month Hobby, plus usage). **OpenAI is separate** —
you still pay OpenAI per tailored resume. Linux hosts cannot run Microsoft
Word, so **PDF download works online; DOCX only works on this Windows PC**.

### 1. Put the code on GitHub

Create a GitHub repo and push this project. **Do not commit** `backend/.env`
or `frontend/.env` (they are already gitignored).

### 2. Create the Railway service

1. Sign up at [railway.com](https://railway.com) with GitHub.
2. **New Project → Deploy from GitHub repo** → select this repo.
3. Railway detects the root `Dockerfile` and `railway.json` automatically.
4. Open the service → **Variables** and add:

   | Variable | Value |
   |---|---|
   | `OPENAI_API_KEY` | your OpenAI key |
   | `OPENAI_MODEL` | `gpt-4o-mini` (recommended: faster/cheaper) |
   | `CORS_ORIGINS` | `*` |
   | `JWT_SECRET` | a long random string (required for sign-in; generate one and keep it stable across deploys) |
   | `GOOGLE_CLIENT_ID` | your Google OAuth client ID (only if you want Google Sign-In) |

   Sign-in on Railway uses a **new empty database**. Local accounts (including Steve Jeff on your PC) do not exist there — register again on the live URL. The name **Steve Jeff** is still treated as administrator.

   For Google Sign-In, add the Railway HTTPS URL under **Authorized JavaScript origins** in Google Cloud (e.g. `https://your-app.up.railway.app`).

5. **Settings → Public Networking → Generate Domain**.
   Your app URL looks like `https://resume-tailor-ai-production.up.railway.app`.
6. **Settings → Resources**: set memory to **2 GB** (Chromium needs it).
7. **Settings → Usage**: set a monthly spending limit so a runaway deploy
   cannot surprise-bill you.

The first build takes several minutes (Node build + Playwright image).
When the health check at `/health` returns OK, open the public URL.

### 3. When you grow past MVP

- Add a **PostgreSQL** plugin in the same Railway project and switch off SQLite.
- Attach a **volume** if you need uploaded files to survive redeploys.
- Point a custom domain at the service from Railway's Networking settings.

## Environment variables

**backend/.env**

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | Your OpenAI API key |
| `OPENAI_MODEL` | Model used for tailoring (default `gpt-4o-mini`) |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins |
| `JWT_SECRET` | Secret used to sign login tokens (required in production) |
| `GOOGLE_CLIENT_ID` | Google Sign-In client ID |
| `TEMP_STORAGE_DIR` | Directory for temporary uploaded/generated files |
| `MAX_UPLOAD_SIZE_MB` | Max CV upload size |

**frontend/.env**

| Variable | Description |
|---|---|
| `VITE_API_BASE_URL` | Base URL of the backend API |

## API endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/resume/templates` | Lists selectable resume templates (slug, name, description, thumbnail URL) for the gallery. |
| `POST` | `/api/resume/upload` | Multipart file upload (`file` field). Extracts and structures CV content, returns `file_id`. |
| `POST` | `/api/resume/tailor` | JSON body `{ file_id, job_description, main_stack, company_name, template_slug }`. Calls OpenAI, returns structured tailored resume. |
| `GET` | `/api/resume/download/{file_id}?format=pdf\|docx` | Renders the tailored resume into the selected template and returns it for download (PDF by default). |
| `GET` | `/api/resume/history` | Resume-generation history (most recent first), from the SQLite database. |

Interactive API docs are available at `http://localhost:8000/docs` while the
backend is running.

## Possible next steps

- [ ] User authentication (the `ResumeRecord.user_id` column is already there)
- [ ] Add automatic cleanup of old temp files (TTL-based)
- [ ] Support multiple job description "variants" per uploaded CV
- [ ] Add basic tests for `cv_parser`, `ai_tailor`, and `template_renderer`
- [ ] More template designs
