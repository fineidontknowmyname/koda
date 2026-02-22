"""
services/intelligence/youtube.py
----------------------------------
YouTubeService — multi-URL transcript fetching with parallel execution.

Changes vs. original
─────────────────────
* get_transcript_for_url(url)    – wraps extract_video_id + get_transcript.
* fetch_many(urls, ...)          – async, parallel via asyncio.gather.
* TOKEN_GUARD (12 000 chars)     – each transcript is hard-capped before
                                   being returned so downstream prompts stay
                                   within a safe token budget.
* fetch_many returns a dict {url: transcript} so callers know which text
  came from which video (needed by the orchestrator's classifier).

Backward compat
────────────────
The old synchronous youtube_service.get_transcript(video_id) still works.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional
from urllib.parse import urlparse, parse_qs

from youtube_transcript_api import YouTubeTranscriptApi

log = logging.getLogger(__name__)

# Hard cap applied to every transcript before returning.
# 12 000 chars ≈ 3 000 tokens (GPT-style 4 chars/token) — safe for most
# LLM context windows and keeps Ollama prompts responsive.
TOKEN_GUARD: int = 12_000


class YouTubeService:
    """Fetch and process YouTube transcripts synchronously or in parallel."""

    # ── Core helpers (unchanged public API) ───────────────────────────────────

    def extract_video_id(self, url: str) -> Optional[str]:
        """
        Extract a video ID from any common YouTube URL format.

        Supports: standard (watch?v=), short (youtu.be/), embed (/embed/),
        and legacy (/v/) URLs.
        """
        parsed = urlparse(url.strip())

        # Standard: https://www.youtube.com/watch?v=VIDEO_ID
        qs = parse_qs(parsed.query)
        if "v" in qs:
            return qs["v"][0]

        # Short: https://youtu.be/VIDEO_ID
        if parsed.hostname in ("youtu.be",):
            path_part = parsed.path.lstrip("/")
            return path_part.split("?")[0] or None

        # Embed / legacy
        parts = parsed.path.split("/")
        if len(parts) >= 3 and parts[1] in ("embed", "v"):
            return parts[2] or None

        return None

    def get_transcript(self, video_id: str) -> Optional[str]:
        """
        Fetch and concatenate the transcript for a single video ID.

        Returns raw text (up to TOKEN_GUARD chars) or None on failure.
        This method is synchronous so it can be used from non-async contexts.
        """
        try:
            entries = YouTubeTranscriptApi.get_transcript(video_id)
            full    = " ".join(e["text"] for e in entries)
            guarded = self._apply_token_guard(full)
            log.debug("Transcript fetched  video_id=%s  chars=%d", video_id, len(guarded))
            return guarded
        except Exception as exc:
            log.warning("Transcript fetch failed  video_id=%s  error=%s", video_id, exc)
            return None

    # ── New higher-level helpers ───────────────────────────────────────────────

    def get_transcript_for_url(self, url: str) -> Optional[str]:
        """
        Convenience wrapper: URL → video ID → transcript (with token guard).

        Returns None when the URL is unparseable or the fetch fails.
        """
        video_id = self.extract_video_id(url)
        if not video_id:
            log.warning("Could not extract video ID from URL: %s", url)
            return None
        return self.get_transcript(video_id)

    async def fetch_many(
        self,
        urls: List[str],
        *,
        skip_failed: bool = True,
    ) -> Dict[str, str]:
        """
        Fetch transcripts for **multiple** YouTube URLs in parallel.

        All blocking transcript API calls are offloaded to threads via
        asyncio.to_thread so the FastAPI event loop is never held.

        Parameters
        ----------
        urls            List of YouTube video URLs (duplicates are de-duped).
        skip_failed     When True (default), URLs whose transcripts cannot be
                        fetched are silently omitted from the result.
                        When False, a failed URL maps to an empty string.

        Returns
        -------
        dict  { url: transcript_text }
              Only successfully-fetched URLs are included when skip_failed=True.
              Ordering matches the de-duped input list.
        """
        unique_urls: List[str] = list(dict.fromkeys(urls))   # preserve order, remove dupes

        async def _fetch_one(url: str) -> tuple[str, Optional[str]]:
            text = await asyncio.to_thread(self.get_transcript_for_url, url)
            return url, text

        results: list[tuple[str, Optional[str]]] = await asyncio.gather(
            *[_fetch_one(u) for u in unique_urls],
            return_exceptions=False,
        )

        output: Dict[str, str] = {}
        for url, text in results:
            if text:
                output[url] = text
            elif not skip_failed:
                output[url] = ""
            else:
                log.info("Skipping failed URL: %s", url)

        log.info(
            "fetch_many: %d/%d URLs succeeded",
            len(output), len(unique_urls),
        )
        return output

    # ── Token guard ────────────────────────────────────────────────────────────

    @staticmethod
    def _apply_token_guard(text: str, limit: int = TOKEN_GUARD) -> str:
        """
        Hard-cap ``text`` to ``limit`` characters.

        Truncation is performed at the last whitespace boundary before
        ``limit`` so words are never split.
        """
        if len(text) <= limit:
            return text
        truncated = text[:limit]
        last_space = truncated.rfind(" ")
        return truncated[:last_space] if last_space > 0 else truncated


# Module-level singleton
youtube_service = YouTubeService()
