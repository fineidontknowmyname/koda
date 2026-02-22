"""
api/routes.py
--------------
Top-level legacy route shim.

The old POST /generate-plan route is preserved as a permanent redirect to
POST /api/v1/plans/generate/pdf so existing frontend clients keep working
without any changes.

Why a redirect and not a proxy?
 - 307 Temporary Redirect preserves the HTTP method (POST stays POST) and
   the request body, so multipart / JSON payloads pass through unchanged.
 - The frontend only needs to follow the redirect — most HTTP clients
   (fetch, axios, requests) do this transparently.

New frontend code should use /api/v1/plans/generate directly.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from api.v1.api import api_router  # noqa: F401  (re-exported for app.include_router)

log = logging.getLogger(__name__)

router = APIRouter()


# ── Legacy redirect ────────────────────────────────────────────────────────────

@router.api_route(
    "/generate-plan",
    methods=["POST", "GET"],
    include_in_schema=True,
    summary="[Legacy] Redirect to /api/v1/plans/generate/pdf",
    description=(
        "**Deprecated.** This route exists solely for backward compatibility "
        "with frontend clients that still call `/generate-plan`.\n\n"
        "It issues a **307 Temporary Redirect** to `POST /api/v1/plans/generate/pdf` "
        "which preserves the request method and body."
    ),
    tags=["Legacy"],
)
async def legacy_generate_plan_redirect() -> RedirectResponse:
    """
    Permanently redirects legacy POST /generate-plan callers to the versioned endpoint.

    307 (not 308) is used so that browsers and HTTP clients re-send the body.
    """
    log.info("Legacy /generate-plan called — redirecting to /api/v1/plans/generate/pdf")
    return RedirectResponse(
        url="/api/v1/plans/generate/pdf",
        status_code=307,
    )
