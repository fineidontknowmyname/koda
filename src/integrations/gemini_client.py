import google.generativeai as genai
import json
import asyncio
from typing import Optional
from src.config.settings import settings
from src.schemas.content import ExerciseLibrary

# Configure the SDK
genai.configure(api_key=settings.GEMINI_API_KEY)

class GeminiClient:
    def __init__(self):
        self.model = genai.GenerativeModel("gemini-1.5-flash")
        
    async def extract_exercises(self, transcript_text: str) -> ExerciseLibrary:
        """
        Extracts structured exercise data from a raw transcript using Gemini 1.5 Flash.
        """
        # Truncate if necessary (Gemini 1.5 has large context, but let's be safe/economical)
        clean_text = transcript_text[:50000] 
        
        prompt = f"""
        You are an expert fitness data analyst.
        Extract all fitness exercises from the following transcript into a structured JSON format.
        
        Rules:
        1. Ignore conversational filler.
        2. Infer muscles worked and difficulty if not explicitly stated.
        3. Identify any specific safety warnings mentioned.
        4. Output MUST be valid JSON matching the schema below.
        5. Do not include markdown formatting (like ```json). Just the raw JSON string.

        Schema:
        {{
            "exercises": [
                {{
                    "name": "string",
                    "description": "string",
                    "instructions": ["step 1", "step 2"],
                    "benefits": ["benefit 1"],
                    "muscles_worked": ["muscle 1"],
                    "equipment_needed": ["dumbbell", "bodyweight", "etc"],
                    "difficulty": "beginner" | "intermediate" | "advanced",
                    "safety_warnings": ["warning 1"]
                }}
            ]
        }}

        Transcript:
        {clean_text}
        """

        try:
            # Run the blocking generation in a thread to keep FastAPI async
            response = await asyncio.to_thread(
                self.model.generate_content, 
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            
            raw_json = response.text
            # Clean up potential markdown code blocks if the model ignores the instruction
            if raw_json.startswith("```json"):
                raw_json = raw_json[7:]
            if raw_json.endswith("```"):
                raw_json = raw_json[:-3]
                
            return ExerciseLibrary.model_validate_json(raw_json.strip())
            
        except Exception as e:
            # In production, we would log this error properly
            print(f"Gemini Extraction Error: {e}")
            # Return empty library on failure to avoid crashing the flow
            return ExerciseLibrary(exercises=[])

gemini_client = GeminiClient()
