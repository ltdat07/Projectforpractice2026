from fastapi import APIRouter, Query

from app import repository
from app.schemas import ActionLogRead


router = APIRouter(prefix="/api/actions", tags=["Action journal"])


@router.get("", response_model=list[ActionLogRead])
def get_actions(
    profile_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    return repository.list_action_logs(profile_id=profile_id, limit=limit)
