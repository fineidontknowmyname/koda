"""
services/vision/model_loader.py
---------------------------------
Singleton .keras model loader for the body composition inference pipeline.

Design goals
────────────
* Load once at first access (lazy init) — FastAPI startup is unaffected.
* Cache the compiled Keras model in module-level memory for the lifetime of
  the process so every inference request reuses the same weights.
* Provide a clean fallback when TensorFlow is not installed or the model file
  does not exist on disk, returning None instead of crashing.
* Expose a ModelRegistry class so future models (e.g. posture classifiers)
  can be added in one place without touching inference code.

Model file convention
──────────────────────
By default the loader expects the .keras file at:

    <project_root>/models/body_composition.keras

Override with the BODY_COMPOSITION_MODEL_PATH env var or via
ModelRegistry.set_path() before the first access.

Usage
─────
    from services.vision.model_loader import model_registry

    model = model_registry.body_composition   # tf.keras.Model | None
    if model is None:
        # TF not installed or weights file missing — fall back to heuristics
        ...
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ── Default paths ──────────────────────────────────────────────────────────────

_HERE         = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[3]   # src/services/vision/ → src/ → project root

_DEFAULT_BODY_COMP_PATH = _PROJECT_ROOT / "models" / "body_composition.keras"


# ── Low-level loader ───────────────────────────────────────────────────────────

def _load_keras_model(path: Path):
    """
    Load a compiled Keras model from *path*.

    Returns the model on success, None on any failure (missing file,
    TensorFlow not installed, corrupt weights, etc.).
    """
    if not path.exists():
        log.warning(
            "Model file not found at %s — inference will use heuristic fallback. "
            "Place a trained .keras file at this path to enable MobileNetV2 inference.",
            path,
        )
        return None

    try:
        import tensorflow as tf  # noqa: F401

        model = tf.keras.saving.load_model(str(path), compile=False)
        log.info("Loaded Keras model from %s  (params: %s)", path, model.count_params())
        return model

    except ImportError:
        log.warning("tensorflow not installed — cannot load model from %s", path)
        return None

    except Exception as exc:
        log.error("Failed to load model from %s: %s", path, exc)
        return None


# ── Singleton registry ─────────────────────────────────────────────────────────

class ModelRegistry:
    """
    Holds lazy-loaded Keras models keyed by name.

    Models are loaded on first property access and cached for the process
    lifetime.  Paths can be overridden before first access via set_path().
    """

    def __init__(self) -> None:
        # Path overrides (can be set before first access)
        self._paths: dict[str, Path] = {
            "body_composition": Path(
                os.environ.get("BODY_COMPOSITION_MODEL_PATH", str(_DEFAULT_BODY_COMP_PATH))
            ),
        }
        # Loaded model cache
        self._cache: dict[str, object] = {}

    # ── Path helpers ──────────────────────────────────────────────────────────

    def set_path(self, name: str, path: str | Path) -> None:
        """
        Override the file path for a named model before it is first loaded.

        Raises RuntimeError if the model has already been cached.
        """
        if name in self._cache:
            raise RuntimeError(
                f"Cannot change path for '{name}' — it has already been loaded. "
                "Restart the process to apply a new path."
            )
        self._paths[name] = Path(path)

    # ── Model accessors ───────────────────────────────────────────────────────

    @property
    def body_composition(self):
        """
        MobileNetV2-based body composition model.

        Returns tf.keras.Model on success, None when TF is absent or the
        weights file does not exist.
        """
        return self._get("body_composition")

    def _get(self, name: str):
        """Load (if needed) and return the named model from cache."""
        if name not in self._cache:
            path = self._paths.get(name)
            if path is None:
                log.error("No path registered for model '%s'", name)
                self._cache[name] = None
            else:
                self._cache[name] = _load_keras_model(path)
        return self._cache[name]

    # ── Pre-warm helper ───────────────────────────────────────────────────────

    def preload_all(self) -> None:
        """
        Force-load every registered model.

        Call this from a FastAPI startup event to warm all models before the
        first request arrives rather than paying the load cost on the hot path.

        Example
        ───────
            @app.on_event("startup")
            async def startup():
                import asyncio
                await asyncio.to_thread(model_registry.preload_all)
        """
        for name in self._paths:
            _ = self._get(name)
            log.info("Pre-loaded model '%s': %s", name, "OK" if self._cache.get(name) else "UNAVAILABLE")

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def status(self) -> dict[str, str]:
        """Return a {name: "loaded" | "not_loaded" | "unavailable"} status map."""
        out: dict[str, str] = {}
        for name, path in self._paths.items():
            if name in self._cache:
                out[name] = "loaded" if self._cache[name] is not None else "unavailable"
            else:
                out[name] = "not_loaded" if path.exists() else "file_missing"
        return out


# ── Module-level singleton ─────────────────────────────────────────────────────

model_registry = ModelRegistry()
