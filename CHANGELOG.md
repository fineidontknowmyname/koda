# Changelog

All notable changes to **FitGen AI (Koda)** are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com).

---

## [2.0.0] — 2026-02-22 — Complete Platform Overhaul

### Summary

FitGen v2.0 is a ground-up rewrite of practically every layer. The LLM backend migrated from Google Gemini (cloud API) to Ollama (self-hosted Mistral / Gemma3). The in-memory user store was replaced by a full SQLAlchemy async ORM backed by SQLite (dev) or PostgreSQL (prod). Plan generation was made asynchronous via Celery + Redis. Six new core calculation engines were added (TDEE, BMI, Protein, Exercise Scorer, Meal Selector, Scheduler). The single-YouTube-URL pipeline became a multi-URL transcript pipeline with video classification. The PDF report expanded from a single section to four sections with body composition data. A complete Next.js frontend was built from scratch covering signup, onboarding, dashboard, and async job polling.

---

### Added

**LLM & Integrations**
- Added `src/integrations/ollama_client.py` — async Ollama REST wrapper (`POST /api/generate`) supporting text generation and vision analysis via llava model; exports a backward-compat `gemini_client` alias
- Added `OLLAMA_HOST`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_VISION_MODEL` settings fields to `src/config/settings.py`

**Core Calculation Engines**
- Added `src/core/tdee.py` — Mifflin-St Jeor BMR (`10w + 6.25h − 5a + 5` male / `−161` female), FAO/WHO/UNU 2001 PAL multipliers (1.20–1.90), goal-based calorie deltas (weight_loss: −500 kcal, muscle_gain: +300 kcal, strength: +200 kcal), 1200 kcal safety floor
- Added `src/core/bmi.py` — WHO BMI categories (8 tiers from severe thinness to obese class III), Devine formula ideal weight (`50.0 kg + 2.3 kg/inch` male, `45.5 kg + 2.3 kg/inch` female), PlanSignal enum (green/caution/warning) for orchestrator
- Added `src/core/protein.py` — ISSN 2017 goal-based protein targets (1.4–2.0 g/kg), capacity-score bonus (0.0–0.2 g/kg), CDC/WHO safety clamping (floor 0.8 g/kg, ceiling 3.5 g/kg), full macro split (protein/fat 25%/carbs remainder)
- Added `src/core/exercise_scorer.py` — 5-factor weighted scoring engine: difficulty_match (0.30), equipment_fit (0.20), muscle_coverage (0.20), goal_alignment (0.20 via keyword intersection), safety_headroom (0.10); outputs ranked `ScoredExercise` list
- Added `src/core/meal_selector.py` — slot-based daily meal planner with 5 slots (breakfast 25%, lunch 30%, snack 10%, dinner 30%, evening snack 5%), 9 dietary restriction tags (vegan through kosher), greedy selection with ±5% calorie tolerance, portion scaling
- Added `src/core/scheduler.py` — weekly workout scheduling with training split logic (push/pull/legs), rest day placement, progressive overload integration

**Database Layer**
- Added `src/db/base.py` — SQLAlchemy async engine + DeclarativeBase
- Added `src/db/models.py` — `UserRecord` (profile stored as JSON blob in `profile_json` column), `FitnessPlanRecord` (plan stored as JSON blob), auto-increment IDs, created_at timestamps
- Added `src/db/session.py` — `AsyncSessionLocal` factory, `get_db()` FastAPI dependency with auto-commit/rollback, `init_db()` for table creation on startup
- Added `src/db/repository.py` — generic CRUD helpers for UserRecord and FitnessPlanRecord

**Async Job Queue**
- Added `src/workers/celery_app.py` — Celery application (broker: Redis DB 0, backend: Redis DB 1), JSON serialisation, `task_acks_late=True` for crash recovery, 24h result TTL
- Added `src/workers/tasks.py` — Celery task wrappers for plan generation pipeline
- Added `src/tasks/plan_tasks.py` — plan generation task orchestration (transcript → exercise extraction → scoring → scheduling → PDF)

**API Endpoints**
- Added `src/api/v1/endpoints/plans.py` — `POST /generate` (async Celery dispatch), `GET /job/{job_id}` (poll status), `GET /job/{job_id}/pdf` (download PDF), legacy sync `POST /generate/pdf`
- Added `src/api/v1/endpoints/users.py` — full CRUD: `POST /` (create), `GET /{user_id}` (read), `PUT /{user_id}` (update), `DELETE /{user_id}` (delete) backed by SQLAlchemy ORM
- Added `src/api/v1/api.py` — v1 router aggregating plans, users, and vision sub-routers

**Schemas**
- Added `src/schemas/metrics.py` — `BodyMetrics` schema (tdee, bmr, calorie_target, protein_g, fat_g, carbs_g, bmi, bmi_category fields)
- Added `src/schemas/responses.py` — API response envelopes (`SuccessResponse`, `ErrorResponse`, `PaginatedResponse`)
- Added `src/schemas/vision.py` — `BodyComposition`, `SWRAnalysis`, `PostureAssessment` schemas for vision pipeline output

**Vision Pipeline**
- Added `src/services/vision/body_composition.py` — MobileNetV2-based body composition analysis, body fat percentage estimation, musculature classification
- Added `src/services/vision/model_loader.py` — lazy model registry for MobileNetV2 weights (.keras format), thread-safe singleton loading
- Added `src/services/intelligence/transcript_service.py` — transcript extraction orchestration layer

**Frontend (entire `frontend/` directory — new)**
- Added `frontend/src/app/page.tsx` — landing page with hero section, gradient animations, Genesis Tech branding
- Added `frontend/src/app/signup/page.tsx` — signup form with age (15–60), weight, height, gender fields
- Added `frontend/src/app/onboarding/page.tsx` — 6-step onboarding wizard (biometrics → activity → baseline → goals → YouTube URLs → photo analysis)
- Added `frontend/src/app/login/page.tsx` — login page
- Added `frontend/src/app/dashboard/page.tsx` — dashboard with plan generation trigger and results display
- Added `frontend/src/app/status/[jobId]/page.tsx` — async job status polling page
- Added `frontend/src/components/JobStatusPoller.tsx` — real-time job status polling component with progress UI
- Added `frontend/src/hooks/useJobStatus.ts` — custom React hook for polling `GET /api/v1/plans/job/{id}` with exponential backoff
- Added `frontend/src/components/layout/Header.tsx` — global navigation header
- Added `frontend/src/components/ui/` — reusable UI primitives (Button, Input, Label, Select)
- Added `frontend/src/lib/api.ts` — API client with typed interfaces (`PlanJobPayload`, `UploadPhotosResult`, `JobStatusResponse`)

**Documentation & Config**
- Added `README.md` — project documentation with setup instructions
- Added `FitGen_Koda_Migration_Map.pdf` — migration planning document
- Added `src/exceptions.py` — domain exception hierarchy (`DomainBaseError`, `ValidationError`, `NotFoundError`, `ExternalServiceError`, etc.)
- Added `debug_mediapipe.py` — MediaPipe debug utility
- Added `tests/verify_biometrics.py` — biometric calculation verification script
- Added `tests/verify_intelligence.py` — transcript intelligence pipeline tests
- Added `tests/verify_orchestrator.py` — orchestrator integration tests
- Added `tests/verify_swr.py` — shoulder-to-waist ratio verification
- Added `tests/verify_vision.py` — vision pipeline verification

---

### Changed

**`requirements.txt`**
- Added ~30 new dependencies: `celery`, `redis`, `aiosqlite`, `sqlalchemy[asyncio]`, `mediapipe`, `opencv-python-headless`, `httpx`, `fpdf2`, `yt-dlp`, `youtube-transcript-api`, `numpy`
- Removed: `google-generativeai`, `langchain-google-genai`

**`.env.example`**
- Removed `GEMINI_API_KEY=your_gemini_api_key_here`
- Added `OLLAMA_HOST=http://localhost:11434`
- Added `REDIS_URL=redis://localhost:6379/0`

**`.gitignore`**
- Added entries for: `*.db`, `.next/`, `/package-lock.json`, `tmp/`, `plans/`, `*.keras`, `*.h5`, `*.tflite`

**`src/config/settings.py`**
- Expanded from 21 lines (only `GEMINI_API_KEY`) to 122 lines
- Added fields: `OLLAMA_HOST`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_VISION_MODEL`, `MODEL_PATH`, `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `ENVIRONMENT`, `DEBUG`
- Added derived properties: `effective_ollama_host`, `effective_broker_url`, `effective_backend_url`
- Changed: `env_file` now resolves to project root `.env` using `Path(__file__).resolve().parent.parent.parent`

**`src/main.py`**
- Expanded from 25 lines (bare FastAPI app) to 230+ lines
- Added lifespan manager: DB init on startup, vision model pre-warm, Ollama connectivity check, Celery worker check
- Added CORS middleware with configurable origins
- Added `GET /health` endpoint returning service readiness status
- Added catch-all `@app.exception_handler(Exception)` returning generic 500 without leaking stack traces
- Added structured logging with `logging.basicConfig`

**`src/api/routes.py`**
- Changed from direct endpoint definitions to legacy redirect shim
- Added `POST /generate-plan` → 307 redirect to `/api/v1/plans/generate/pdf`
- Added `POST /signup` → 307 redirect to `/api/v1/users/`

**`src/api/dependencies.py`**
- Expanded from 4 lines (empty stub) to 110+ lines of auth/dependency injection utilities

**`src/api/v1/endpoints/vision.py`**
- Expanded from 92 lines (single image analysis) to 264+ lines
- Added 3-photo body composition upload endpoint (`POST /analyze`)
- Added MediaPipe landmark analysis with shoulder-to-waist ratio calculation
- Added `X-Consent: body-analysis` header enforcement for GDPR compliance
- Added response schemas with `BodyComposition`, `SWRAnalysis`, `PostureAssessment`

**`src/core/orchestrator.py`**
- Expanded from 62 lines (single-URL pipeline) to 432+ lines
- Changed single YouTube URL input to multi-URL list processing
- Added exercise cherry-picking via `ExerciseScorer.score_and_rank()` with top-N selection
- Added TDEE enrichment: BMR, TDEE, calorie target injected into plan metadata
- Added macro split injection (protein/fat/carbs) from `ProteinEngine`
- Added body composition data injection from vision pipeline results
- Added diet plan generation via `MealSelectorEngine`
- Added BMI analysis and plan signal (green/caution/warning) integration

**`src/core/capacity.py`**
- Expanded from 36 lines (basic pushup/situp/squat score) to 225+ lines
- Added progressive overload logic with 1RM estimation (Epley formula)
- Added volume prescription (sets × reps targets) based on capacity score
- Added training age estimation from capacity metrics

**`src/core/progression.py`**
- Changed import path from `schemas.user` to updated module structure (4 lines changed)

**`src/core/safety.py`**
- Changed import path from `schemas.user` to updated module structure (4 lines changed)

**`src/integrations/vision_analyzer.py`**
- Expanded from 64 lines to 564+ lines
- Added MobileNetV2 body composition analysis pipeline
- Added MediaPipe pose detection with 33-landmark model
- Added body fat percentage estimation from silhouette analysis
- Added V-taper ratio calculation (shoulder width / waist width)
- Added posture assessment from landmark angles

**`src/reporting/pdf_architect.py`**
- Expanded from 72 lines (single-section PDF) to 573+ lines (4-section PDF)
- Added Section 1: User metrics summary (age, weight, height, BMI, BMR, TDEE, calorie target)
- Added Section 2: Weekly workout tables with day/exercise/sets/reps/rest columns
- Added Section 3: 7-day diet plan with meal slot breakdown and macro totals
- Added Section 4: Training guide with safety recommendations
- Added body composition subsection: SWR category, body fat %, V-taper ratio
- Added colour-coded FPDF2 table styling

**`src/schemas/common.py`**
- Added `ActivityLevel` enum: `sedentary`, `lightly_active`, `moderately_active`, `very_active`, `extra_active`
- Added `MuscleLevel` enum for body composition classification
- Added `BodyType` enum for physique categorisation
- Changed `Gender` enum: removed `OTHER` value (now only `male`, `female`)

**`src/schemas/content.py`**
- Expanded `Exercise` model with scoring fields: `difficulty`, `equipment_needed`, `safety_warnings`, `muscles_worked`
- Added `VideoCategory` enum: `workout`, `diet`, `motivation`, `other`
- Added `ClassifiedVideo` model for multi-URL pipeline output

**`src/schemas/plan.py`**
- Added `GeneratePlanRequest` with `youtube_urls: List[str]` (multi-URL) and backward-compat `youtube_url: Optional[str]` single-URL alias
- Added `JobResponse`, `JobStatus` enum (`pending`, `started`, `success`, `failure`), `JobStatusResponse`
- Added `FitnessPlan.body_composition` field for vision pipeline data

**`src/schemas/user.py`**
- Added `PhysicalActivity` model with `activity_level` (default: `moderately_active`) and `physical_activity_hours_per_day` (default: `1.0`, range 0.0–16.0)
- Added `analysis_consent` boolean field to `UserProfile`
- Added `@field_validator("age")` — `clamp_age`: forces age into 15–60 range instead of rejecting out-of-range values
- Added `@field_validator("gender")` — `normalise_gender`: maps unrecognised gender values to `"male"` instead of rejecting
- Changed `UserProfile.physical_activity` from required to `Optional[PhysicalActivity] = None`

**`src/services/analyst.py`**
- Expanded from 0 lines (empty placeholder) to 49 lines of structured analysis pipeline

**`src/services/fitness/engine.py`**
- Expanded from 0 lines (empty placeholder) to 186 lines
- Added exercise selection via `ExerciseScorer` with top-N cherry-picking
- Added progressive overload parameter generation
- Added weekly schedule assembly via `Scheduler`

**`src/services/intelligence/summarizer.py`**
- Expanded from 0 lines (empty placeholder) to 271 lines
- Added Ollama-powered transcript summarisation with exercise extraction
- Added structured JSON output parsing with fallback for malformed LLM responses

**`src/services/intelligence/youtube.py`**
- Expanded from 0 lines (empty placeholder) to 169 lines
- Added multi-URL transcript fetching via `youtube-transcript-api`
- Added video classification into categories (workout/diet/motivation)

**`src/services/vision/landmarks.py`**
- Expanded from 0 lines (empty placeholder) to 133 lines
- Added MediaPipe pose landmark detection (33 body landmarks)
- Added shoulder-to-waist ratio measurement from landmark coordinates
- Added SWR category classification (narrow / average / broad / very broad)

---

### Removed

- Removed `src/integrations/gemini_client.py` — replaced entirely by `src/integrations/ollama_client.py` (LLM provider migration from Google Gemini cloud API to self-hosted Ollama)
- Removed `src/utils/pdf_gen.py` — empty placeholder file replaced by `src/reporting/pdf_architect.py`
- Removed `GEMINI_API_KEY` from `.env.example` and `src/config/settings.py`
- Removed `Gender.OTHER` from `src/schemas/common.py` (now only `male` / `female`)

---

### Fixed

- Fixed `frontend/src/app/onboarding/page.tsx` activity level dropdown values sending `light`, `moderate`, `active` instead of `lightly_active`, `moderately_active`, `very_active` (caused 422 Unprocessable Entity on plan generation)
- Fixed `frontend/src/app/onboarding/page.tsx` default `activityLevel` form value from `moderate` to `moderately_active`
- Fixed `src/api/v1/endpoints/users.py` referencing `row.profile` instead of `row.profile_json` (caused 500 Internal Server Error on user profile creation — ORM column name mismatch)
- Fixed `src/api/v1/endpoints/users.py` missing `await db.commit()` in `create_user_profile` (flush alone didn't persist data through the session lifecycle)
- Fixed `src/schemas/user.py` age validation rejecting values outside 15–60 with 422 instead of clamping gracefully
- Fixed `src/schemas/user.py` gender validation rejecting non-male/female values with 422 instead of normalising to default
- Fixed `src/services/fitness/engine.py` missing `import numpy` (NameError at runtime)

---

### Technical Details

**Formulae Implemented**
- **BMR**: Mifflin-St Jeor — `10w + 6.25h − 5a + 5` (male) / `10w + 6.25h − 5a − 161` (female)
- **PAL**: FAO/WHO/UNU 2001 — sedentary 1.200, lightly active 1.375, moderate 1.550, very active 1.725, extra active 1.900; bonus +0.025/hr beyond 0.5h capped at 1.90
- **TDEE**: BMR × PAL; calorie target = TDEE + goal delta (−500 weight loss, +300 muscle, +200 strength); floor 1200 kcal
- **BMI**: weight_kg / height_m²; classified into 8 WHO categories
- **Ideal Weight**: Devine 1974 — `50.0 + 2.3 × (height_inches − 60)` male, `45.5 + 2.3 × (height_inches − 60)` female; floor 30 kg
- **Protein**: ISSN 2017 — 1.4–2.0 g/kg by goal + capacity bonus 0.0–0.2 g/kg; CDC clamped 0.8–3.5 g/kg
- **Macros**: Fat = 25% of calorie target / 9 kcal/g; Carbs = remainder / 4 kcal/g
- **Exercise Scoring**: 5-factor weighted composite — difficulty (0.30), equipment (0.20), muscle coverage (0.20), goal alignment (0.20), safety (0.10)
- **1RM Estimation**: Epley formula in capacity engine
- **SWR**: shoulder_width / waist_width from MediaPipe landmark coordinates

**Architecture Changes**
- **Sync → Async**: All database operations use `asyncio` + `aiosqlite` (dev) or `asyncpg` (prod)
- **In-memory → ORM**: `fake_user_db` dict replaced by SQLAlchemy `UserRecord` / `FitnessPlanRecord` tables
- **Single URL → Multi-URL**: YouTube pipeline accepts `List[str]` of URLs, processes each transcript independently, merges exercises
- **Sync plan gen → Async**: Plan generation dispatched to Celery worker, frontend polls `GET /job/{id}` for completion
- **1-section PDF → 4-section PDF**: Metrics summary, weekly workout, 7-day diet, training guide
- **Cloud LLM → Self-hosted**: Gemini API calls replaced by local Ollama REST calls (no API key required)

**Dependencies Added**
`celery`, `redis`, `aiosqlite`, `sqlalchemy[asyncio]`, `mediapipe`, `opencv-python-headless`, `httpx`, `fpdf2`, `yt-dlp`, `youtube-transcript-api`, `numpy`, `Pillow`, `pydantic-settings`

**Dependencies Removed**
`google-generativeai`, `langchain-google-genai`, `openai`

---

## [1.0.0] — 2026-02-13 — Initial Release

### Summary

Initial scaffold of the FitGen application with a Gemini-powered LLM backend, single YouTube URL support, basic exercise extraction, and a minimal FastAPI structure. Most service and endpoint files were committed as empty placeholders, with core logic in the orchestrator, capacity scorer, safety filter, and progression engine.

### Added

- Added `src/integrations/gemini_client.py` — Google Gemini API client (76 lines) for exercise extraction and image analysis using `google-generativeai` SDK
- Added `src/integrations/vision_analyzer.py` — initial vision analysis module (64 lines) for MediaPipe pose detection
- Added `src/core/orchestrator.py` — pipeline orchestrator (62 lines) coordinating YouTube transcript → Gemini extraction → plan assembly with single URL input
- Added `src/core/capacity.py` — basic capacity scorer (36 lines) computing composite fitness score from pushup, situp, squat counts
- Added `src/core/safety.py` — safety filter (50 lines) flagging exercises with contraindications based on user profile
- Added `src/core/progression.py` — progression engine (43 lines) adjusting sets, reps, and load based on training week and capacity score
- Added `src/reporting/pdf_architect.py` — single-section PDF generator (72 lines) using FPDF2
- Added `src/schemas/common.py` — base enums: `Gender` (male/female/other), `ExperienceLevel`, `FitnessGoal`, `Equipment`
- Added `src/schemas/content.py` — `Exercise` and `ExerciseLibrary` Pydantic models (16 lines)
- Added `src/schemas/plan.py` — `FitnessPlan` schema (32 lines)
- Added `src/schemas/user.py` — `UserMetrics` and `UserProfile` schemas (24 lines)
- Added `src/config/settings.py` — Pydantic BaseSettings with `GEMINI_API_KEY` (21 lines)
- Added `src/main.py` — bare FastAPI app with uvicorn entrypoint (25 lines)
- Added `src/api/routes.py` — initial route definitions (38 lines) with `/generate-plan` endpoint
- Added `src/api/dependencies.py` — dependency injection stub (4 lines)
- Added `src/api/v1/endpoints/vision.py` — initial vision endpoint (92 lines, added in follow-up commit `fcb13d8`)
- Added `.gitignore` — Python, Node, IDE, environment file exclusions (141 lines)
- Added `.env.example` — `GEMINI_API_KEY`, `DATABASE_URL`, `ENVIRONMENT`
- Added `requirements.txt` — initial Python dependencies
- Added empty placeholder files: `src/api/v1/api.py`, `src/api/v1/endpoints/plans.py`, `src/api/v1/endpoints/users.py`, `src/schemas/vision.py`, `src/services/analyst.py`, `src/services/fitness/engine.py`, `src/services/intelligence/summarizer.py`, `src/services/intelligence/youtube.py`, `src/services/vision/landmarks.py`, `src/core/security.py`, `src/utils/pdf_gen.py`
