# FitGen AI — Koda

> **AI-powered personalised fitness plan generator.**
> Upload body photos, paste YouTube fitness videos, and get a fully personalised 4-week workout plan + 7-day diet plan as a downloadable PDF — all running locally on your machine with no external AI API costs.

---

## What It Does

You provide:
- Your age, height, weight, fitness level, goals, equipment, injuries
- How many hours/day you are physically active
- 1–5 YouTube links (workout videos, diet videos, exercise tutorials)
- Optionally: 3 body photos (front / side / back) for body composition analysis

FitGen gives you:
- A **4-week progressive workout plan** tailored to your benchmarks and goals
- A **7-day personalised diet plan** with calorie targets and macro breakdown
- A **body composition analysis** (estimated body fat %, muscle level, shoulder-to-waist ratio)
- A **downloadable PDF** with all 4 sections ready to follow

Everything runs locally. No OpenAI. No Gemini. No subscription.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + Python 3.11 |
| LLM | Ollama (Gemma 3 / Mistral 7B — local) |
| Vision | MobileNetV2 + MediaPipe (local) |
| Task Queue | Celery + Redis |
| Database | SQLAlchemy + SQLite |
| PDF | ReportLab |
| Frontend | Next.js 16 + React 19 + Tailwind CSS v4 |
| YouTube | youtube-transcript-api |

---

## Architecture

```
Browser (Next.js)
      │
      ▼
FastAPI Backend
      │
      ├── POST /api/v1/plans/generate
      │         │
      │         ▼
      │    Celery Worker (async)
      │         │
      │         ├── 1. Fetch YouTube transcripts (parallel)
      │         ├── 2. Classify videos (Ollama)
      │         ├── 3. Extract exercises + meals (Ollama)
      │         ├── 4. Compute BMI + TDEE + protein targets
      │         ├── 5. Score + cherry-pick exercises
      │         ├── 6. Build 4-week split schedule
      │         ├── 7. Build 7-day diet plan
      │         ├── 8. Render 4-section PDF (ReportLab)
      │         └── 9. Mark job SUCCESS
      │
      ├── GET /api/v1/plans/jobs/{id}  ← frontend polls this
      │
      └── POST /api/v1/vision/analyze-body
                │
                └── MediaPipe pose → shoulder-to-waist ratio
                    MobileNetV2 → body fat % + muscle level
```

---

## PDF Output — 4 Sections

| Section | Content |
|---|---|
| 1 — User Metrics | BMI, TDEE, daily calorie target, macro targets (protein/carbs/fat), ideal weight reference, body composition summary, shoulder-to-waist ratio |
| 2 — 4-Week Workout Plan | Weekly split, exercise tables with sets/reps/weight, form cues, source video attribution, weekly progression |
| 3 — 7-Day Diet Plan | Meal table (breakfast/lunch/dinner/snack), per-meal macros, daily calorie totals, dietary restriction flags |
| 4 — Exercise Reference | One entry per exercise: form cues, common mistakes, progression tips, 4-week volume table |

---

## Prerequisites

Install these before running the app:

| Tool | Purpose | Install |
|---|---|---|
| Python 3.11+ | Backend runtime | python.org |
| Node.js 20+ | Frontend runtime | nodejs.org |
| Ollama | Local LLM server | ollama.com |
| Redis | Celery message broker | See below |

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/fineidontknowmyname/koda.git
cd koda
```

### 2. Backend setup

```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment variables

```bash
# Copy the example file
copy .env.example .env      # Windows
cp .env.example .env        # Mac/Linux

# Edit .env with your values
```

Required `.env` values:

```env
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=gemma3:4b
REDIS_URL=redis://localhost:6379/0
DATABASE_URL=sqlite:///./koda.db
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

### 4. Pull the Ollama model

```bash
# Install Ollama from ollama.com, then:
ollama pull gemma3:4b
```

Choose your size based on your machine:

| Model | Size | Speed on CPU |
|---|---|---|
| gemma3:1b | ~800MB | Fastest |
| gemma3:4b | ~2.5GB | Recommended ✅ |
| gemma3:12b | ~7GB | Slow on CPU |

### 5. Install Redis (Windows)

Download and run the installer:
```
https://github.com/microsoftarchive/redis/releases/download/win-3.0.504/Redis-x64-3.0.504.msi
```

Verify it works:
```powershell
redis-cli ping
# Should return: PONG
```

Mac/Linux:
```bash
brew install redis && redis-server   # Mac
sudo apt install redis-server        # Linux
```

### 6. Frontend setup

```bash
cd frontend
npm install
```

### 7. Database initialisation

```bash
# From koda/ root
python -c "from src.db.base import Base; from src.db.session import engine; Base.metadata.create_all(engine)"
```

---

## Running the App

Open **4 terminals** from the `koda/` root:

```bash
# Terminal 1 — Ollama (LLM server)
ollama serve

# Terminal 2 — Redis (already running as Windows service)
# Nothing to do — Redis starts automatically on Windows
# On Mac/Linux: redis-server

# Terminal 3 — Celery worker (background job processor)
celery -A src.workers.celery_app worker --loglevel=info --pool=solo

# Terminal 4 — FastAPI backend
uvicorn src.main:app --reload --port 8000
```

```bash
# Terminal 5 — Next.js frontend
cd frontend
npm run dev
```

Open your browser at: **http://localhost:3000**

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/users/` | Create user account |
| POST | `/api/v1/users/login` | Login + get JWT token |
| POST | `/api/v1/plans/generate` | Submit plan job → returns job_id |
| GET | `/api/v1/plans/jobs/{id}` | Poll job status |
| GET | `/api/v1/plans/jobs/{id}/pdf` | Download completed PDF |
| POST | `/api/v1/vision/analyze-body` | Upload 3 photos → body composition |
| GET | `/health` | Service health check |

---

## How Plan Generation Works

**Step 1 — Submit:**
```
POST /api/v1/plans/generate
→ Returns: { job_id: "abc123", status: "PENDING" }
```

**Step 2 — Poll every 3 seconds:**
```
GET /api/v1/plans/jobs/abc123
→ Returns: { status: "STARTED" }  (processing...)
→ Returns: { status: "SUCCESS" }  (done — download PDF)
```

**Step 3 — Download:**
```
GET /api/v1/plans/jobs/abc123/pdf
→ Returns: PDF file stream
```

Plan generation takes **1–5 minutes** on CPU depending on how many YouTube videos you provide. The frontend shows live progress labels while you wait.

---

## Body Composition Analysis

Upload 3 photos (front / side / back) during onboarding:

- **Estimated body fat %** — shown as a range (e.g. 18–24%)
- **Muscle level** — scored 1–5
- **Body type** — ectomorph / lean / athletic / average / heavy
- **Shoulder-to-waist ratio** — measured via MediaPipe pose landmarks
  - SWR > 1.2 → Athletic (V-taper) — plan intensity increased
  - SWR 1.0–1.2 → Balanced — standard plan
  - SWR < 1.0 → Waist wider than shoulders — extra cardio day added

> **Note:** Body composition uses a stub model for now. Results are estimates. The vision pipeline is fully wired and ready — drop a trained `.keras` model into `models/` to activate real inference.

---

## Formulas Used

| Calculation | Formula |
|---|---|
| BMR | Mifflin-St Jeor (gender-specific) |
| TDEE | BMR × activity multiplier (6 levels, mapped from hours/day) |
| Protein target | Goal-based g/kg: 1.3 (weight loss) → 1.9 (muscle gain) |
| Macro split | Protein-first: fix protein → split remaining kcal into carbs/fat by goal |
| BMI | Quetelet: weight / height² |
| Ideal weight | Devine formula ± 10% (shown as reference only) |
| Capacity score | Weighted benchmark average + BMI adj + activity bonus + muscle bonus |

---

## Project Structure

```
koda/
├── src/
│   ├── main.py                    # FastAPI app + lifespan manager
│   ├── exceptions.py              # Domain exception hierarchy
│   ├── api/
│   │   ├── routes.py              # Legacy redirect shim
│   │   ├── dependencies.py        # DI providers
│   │   └── v1/endpoints/
│   │       ├── plans.py           # Async job dispatch + polling
│   │       ├── users.py           # User CRUD
│   │       └── vision.py          # Body composition upload
│   ├── core/
│   │   ├── orchestrator.py        # 14-step plan pipeline
│   │   ├── capacity.py            # Intensity score (0.5–1.5)
│   │   ├── exercise_scorer.py     # 5-factor cherry-picking
│   │   ├── scheduler.py           # Split-based workout scheduler
│   │   ├── meal_selector.py       # 7-day diet plan builder
│   │   ├── progression.py         # 4-week progressive overload
│   │   ├── safety.py              # Injury + equipment filter
│   │   ├── tdee.py                # BMR + TDEE calculation
│   │   ├── protein.py             # Protein + macro targets
│   │   └── bmi.py                 # BMI + ideal weight
│   ├── db/                        # SQLAlchemy ORM layer
│   ├── integrations/
│   │   └── ollama_client.py       # Gemma3/Mistral LLM client
│   ├── schemas/                   # Pydantic models
│   ├── services/
│   │   ├── intelligence/          # YouTube + transcript + summarizer
│   │   └── vision/                # MediaPipe + body composition
│   ├── reporting/pdf_architect.py # 4-section PDF renderer
│   ├── tasks/                     # Celery task definitions
│   └── workers/                   # Celery app config
└── frontend/
    └── src/
        ├── app/                   # Next.js pages
        ├── components/            # UI components
        ├── hooks/useJobStatus.ts  # Job polling hook
        └── lib/api.ts             # API client functions
```

---

## Roadmap

- [ ] Train MobileNetV2 body composition model on real dataset
- [ ] Replace SQLite with PostgreSQL for multi-user support
- [ ] Add real JWT auth (currently localStorage)
- [ ] Docker + docker-compose for one-command setup
- [ ] Deploy to VPS / Railway
- [ ] Add Sentry error monitoring
- [ ] Rate limiting on plan generation endpoint
- [ ] Support for more Ollama models (configurable via .env)

---

## Known Limitations

- **Body composition is stubbed** — returns realistic dummy values until a trained model is placed in `models/`
- **CPU inference is slow** — Ollama on CPU takes 1–5 min per plan depending on video count
- **Windows Celery** — must use `--pool=solo` flag on Windows
- **YouTube captions** — ~15% of videos have disabled captions and will be skipped gracefully

---

## Contributing

This is a personal project. If you find bugs or want to suggest improvements, open an issue.

---

## License

MIT

---

*Built with FastAPI, Ollama, Celery, MediaPipe, ReportLab, and Next.js.*
