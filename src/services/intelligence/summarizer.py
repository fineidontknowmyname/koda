"""
services/intelligence/summarizer.py
-------------------------------------
Intelligence layer that classifies YouTube video transcripts and extracts
structured exercise / meal data via the Ollama LLM.

Replaces the old prose-summarizer with three focused methods:

  classify_video(transcript)      -> VideoCategory
  extract_exercises(transcript)   -> ExerciseLibrary
  extract_meals(transcript)       -> List[MealItem]

The legacy summarize_content() shim is kept for any callers that haven't
migrated yet — it now calls classify_video + extract_exercises internally
and returns a human-readable digest.

Public API
──────────
from services.intelligence.summarizer import summarizer_service

category = await summarizer_service.classify_video(text)
library  = await summarizer_service.extract_exercises(text)
meals    = await summarizer_service.extract_meals(text)
"""

from __future__ import annotations

import json
import logging
from enum import Enum
from typing import List, Optional

from integrations.ollama_client import ollama_client
from schemas.content import ExerciseLibrary
from core.meal_selector import MealItem, DietaryRestriction

log = logging.getLogger(__name__)

# ── Token cap shared with YouTubeService.TOKEN_GUARD ──────────────────────────
_MAX_CHARS = 12_000


# ── Video category enum ───────────────────────────────────────────────────────

class VideoCategory(str, Enum):
    workout    = "workout"
    diet       = "diet"
    motivation = "motivation"
    general    = "general"


# ── Prompts ───────────────────────────────────────────────────────────────────

_CLASSIFY_PROMPT = """\
Classify this YouTube video transcript into EXACTLY ONE category.
Categories: workout, diet, motivation, general
Reply with only the single lowercase category word and nothing else.

Transcript:
{text}"""

_EXERCISES_PROMPT = """\
You are an expert fitness data analyst.
Extract all fitness exercises from the transcript below as valid JSON.
Do NOT include markdown fences. Output only raw JSON.

Schema:
{{
  "exercises": [
    {{
      "name": "string",
      "description": "string",
      "instructions": ["step 1"],
      "benefits": ["benefit 1"],
      "muscles_worked": ["muscle name"],
      "equipment_needed": ["bodyweight"],
      "difficulty": "beginner" | "intermediate" | "advanced",
      "safety_warnings": ["warning"]
    }}
  ]
}}

Transcript:
{text}"""

_MEALS_PROMPT = """\
You are a certified nutritionist.
Extract every specific food item or meal mentioned in the transcript below as valid JSON.
Do NOT include markdown fences. Output only raw JSON.

Schema:
{{
  "meals": [
    {{
      "name": "string",
      "kcal": <number>,
      "protein_g": <number>,
      "carbs_g": <number>,
      "fat_g": <number>,
      "restriction_tags": ["vegan", "gluten_free"]
    }}
  ]
}}

If kcal / macros are not mentioned, estimate reasonable values.
Valid restriction_tags: vegan, vegetarian, gluten_free, dairy_free, nut_free,
                        low_sodium, low_carb, halal, kosher.

Transcript:
{text}"""


# ── Engine ─────────────────────────────────────────────────────────────────────

class SummarizerService:
    """
    Structured intelligence extraction from transcript text via Ollama.

    All methods are async and apply the TOKEN_GUARD before building prompts.
    """

    # ── Primary methods ───────────────────────────────────────────────────────

    async def classify_video(self, transcript: str) -> VideoCategory:
        """
        Ask the LLM to classify a transcript into one of four categories.

        Returns VideoCategory.general on any ambiguity or error.
        """
        if not transcript:
            return VideoCategory.general

        snippet = self._guard(transcript)
        prompt  = _CLASSIFY_PROMPT.format(text=snippet)

        try:
            raw   = await ollama_client.generate_text(prompt)
            label = raw.strip().lower().split()[0]
            return VideoCategory(label)
        except (ValueError, IndexError):
            log.debug("classify_video: unrecognised label; defaulting to general")
            return VideoCategory.general
        except Exception as exc:
            log.warning("classify_video failed: %s", exc)
            return VideoCategory.general

    async def extract_exercises(self, transcript: str) -> ExerciseLibrary:
        """
        Extract structured exercise data from a workout-type transcript.

        Delegates to OllamaClient.extract_exercises() which already contains
        the JSON-mode prompt; this wrapper applies the shared token guard and
        adds the structured fallback.
        """
        if not transcript:
            return ExerciseLibrary(exercises=[])

        guarded = self._guard(transcript)

        try:
            # Use the dedicated extraction path on the client (json_mode=True)
            return await ollama_client.extract_exercises(guarded)
        except Exception as exc:
            log.warning("extract_exercises failed: %s", exc)
            return ExerciseLibrary(exercises=[])

    async def extract_meals(self, transcript: str) -> List[MealItem]:
        """
        Extract meal / food items mentioned in a diet-classified transcript.

        Returns a list of MealItem objects ready for MealSelectorEngine.
        Returns an empty list on failure or when nothing is found.
        """
        if not transcript:
            return []

        snippet = self._guard(transcript)
        prompt  = _MEALS_PROMPT.format(text=snippet)

        try:
            raw_json = await ollama_client.generate_text(prompt, json_mode=True)
            raw_json = self._strip_fences(raw_json)
            data     = json.loads(raw_json)
            meals    = []

            for item in data.get("meals", []):
                tags_raw = item.get("restriction_tags", [])
                tags: set[DietaryRestriction] = set()
                for t in tags_raw:
                    try:
                        tags.add(DietaryRestriction(t))
                    except ValueError:
                        pass   # ignore unknown tags

                meals.append(MealItem(
                    name=str(item.get("name", "Unnamed meal")),
                    kcal=float(item.get("kcal", 0)),
                    protein_g=float(item.get("protein_g", 0)),
                    carbs_g=float(item.get("carbs_g", 0)),
                    fat_g=float(item.get("fat_g", 0)),
                    restriction_tags=tags,
                ))

            log.debug("extract_meals: found %d meals", len(meals))
            return meals

        except Exception as exc:
            log.warning("extract_meals failed: %s", exc)
            return []

    # ── Legacy shim (backward compat) ─────────────────────────────────────────

    async def summarize_content(self, text: str, focus: str = "general") -> str:
        """
        Kept for callers that haven't migrated to the structured methods yet.

        Now produces a structured digest:
          - Classifies the video.
          - Extracts exercises (if workout) or meals (if diet).
          - Returns a human-readable text summary.
        """
        if not text:
            return "No content to summarize."

        category = await self.classify_video(text)
        lines: List[str] = [f"Video category: {category.value}"]

        if category == VideoCategory.workout:
            library = await self.extract_exercises(text)
            if library.exercises:
                names = ", ".join(ex.name for ex in library.exercises[:10])
                lines.append(f"Exercises found ({len(library.exercises)}): {names}")
            else:
                lines.append("No structured exercises extracted.")

        elif category == VideoCategory.diet:
            meals = await self.extract_meals(text)
            if meals:
                names = ", ".join(m.name for m in meals[:8])
                lines.append(f"Meals/foods found ({len(meals)}): {names}")
            else:
                lines.append("No specific meals extracted.")

        return "\n".join(lines)

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _guard(text: str) -> str:
        """Apply the 12k-char token guard at a word boundary."""
        if len(text) <= _MAX_CHARS:
            return text
        truncated  = text[:_MAX_CHARS]
        last_space = truncated.rfind(" ")
        return truncated[:last_space] if last_space > 0 else truncated

    @staticmethod
    def _strip_fences(text: str) -> str:
        """Remove ```json / ``` Markdown fences that some models emit."""
        t = text.strip()
        if t.startswith("```json"):
            t = t[7:]
        elif t.startswith("```"):
            t = t[3:]
        if t.endswith("```"):
            t = t[:-3]
        return t.strip()


# Module-level singleton
summarizer_service = SummarizerService()
