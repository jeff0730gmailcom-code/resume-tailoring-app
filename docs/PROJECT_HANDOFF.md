# Resume Tailor AI — handoff for a new Cursor account

Use this file as the starting context. Full raw chats are in `docs/cursor-chat-history/agent-transcripts/`.

## What this app is

Web app: upload a master CV + job description + pick a template → AI tailors content → preview PDF → download PDF/DOCX.

- **Frontend:** React + Vite + Tailwind (`frontend/`), API base from `VITE_API_BASE_URL` (dev: `http://localhost:8090`)
- **Backend:** FastAPI (`backend/`), run with uvicorn on **port 8090** (not 8000)
- **DB:** SQLite `backend/data/app.db` — template gallery + history. No user auth yet.
- **AI:** OpenAI via `backend/.env`. Mode: `TAILORING_MODE=aggressive_match`

## How to run locally

```bash
# backend (no --reload — Playwright/Windows)
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8090

# frontend
cd frontend
npm run dev -- --port 5173 --host 127.0.0.1
```

- App: http://127.0.0.1:5173/
- API: http://localhost:8090

PDF rendering: Playwright bundled Chromium often fails to download. `template_renderer.py` falls back to **system Chrome**, then **Edge**.

## Tailoring method (current)

**Kept from master CV (identity):** contact, job titles, companies, dates, education, certifications. Same jobs; no extra employers invented.

**AI-generated for the JD (not limited to CV bullets/skills):**
- Professional summary
- Skills list (any JD-relevant skill; then `normalize_ai_skills` only dedupes/casing)
- Exactly **8 bullets per job**, fully JD-driven (original CV bullets are **not** used; prompt does not send original bullets)

Languages section is fixed: `English — C1`.

**Deterministic (no AI):** CV parse, JD analysis, resume matching, company/date restore, bullet pad/trim to 8, ATS score, filename, PDF render.

**Filename rule:** `{Candidate Name}_{Stack}_{Company}`  
Example: `Mateo Baranji_Java_Sequencer.pdf`  
Spaces stay **inside** the name; `_` only joins the three parts.  
Preview iframe must wrap the PDF `Blob` in a `File` with that name, or Chrome’s viewer download becomes a UUID.

## Templates

Gallery from SQLite, seeded from `backend/app/templates/resumes/<slug>/`.

| slug | UI name |
|------|---------|
| dejan | Modern Green |
| marek | Classic Serif |
| mateo | Bold Header |
| nemanja | Centered Rule |
| quang | Teal Centered |

Master CV is **content only**. Selected template is **layout only**. Preview uses the same Playwright PDF as download (`GET /api/resume/preview/{file_id}`).

**Classic Serif (`marek`):** section/job/education titles are **sans-serif (Arial)**; body is Georgia serif. Job header is a **table** (not flex) so Chromium PDF does not merge the first bullet onto the title line.

Template picker: click a card → select + **full-screen modal** of the sample thumbnail.

## Key files

- Prompts: `backend/app/prompts/resume_tailor_prompt.py` (never inline in routes)
- AI call: `backend/app/services/ai_tailor.py`
- Skills cleanup: `backend/app/services/resume_validator.py` (`normalize_ai_skills`)
- Filenames: `backend/app/services/filename_generator.py`
- PDF: `backend/app/services/template_renderer.py`
- Routes: `backend/app/api/routes/resume.py`
- Rules: `.cursor/rules/resume-tailor-code-standards.mdc`, `resume-tailoring-prompt-rules.mdc`

## Deploy (not done yet)

No Docker in repo. For public use: Linux VPS + nginx + HTTPS. Playwright Chromium on Linux. **DOCX needs Word COM (Windows)** — Linux = PDF only. **No auth** — anyone with the URL uses **your** OpenAI key.

## What not to break

- Secrets only via `backend/app/core/config.py` / `.env`
- Prompts stay in `backend/app/prompts/`
- Do not commit `.env` or API keys
