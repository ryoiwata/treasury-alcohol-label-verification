"""History routes.

Phase 6 returns an empty history response. Phase 9 replaces this with SQLite.
"""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import HistoryResponse

router = APIRouter(tags=["history"])

_ALLOWED_STATUSES = {"PASS", "REVIEW_NEEDED", "FAIL"}


@router.get("/history", response_model=HistoryResponse)
async def get_history(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Literal["PASS", "REVIEW_NEEDED", "FAIL"] | None = None,
) -> HistoryResponse:
    """Return paginated verification history.

    Phase 6 stub returns no records.
    """
    if status is not None and status not in _ALLOWED_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid status filter")

    return HistoryResponse(total=0, limit=limit, offset=offset, results=[])
