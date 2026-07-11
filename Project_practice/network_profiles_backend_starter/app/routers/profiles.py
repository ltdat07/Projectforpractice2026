from fastapi import APIRouter, HTTPException, Query, Response, status

from app import repository
from app.config import get_core_mode
from app.core_manager import (
    CoreAlreadyRunningError,
    CoreManagerError,
    CoreUnavailableError,
    CoreValidationError,
    core_manager,
)
from app.schemas import (
    CoreValidationRead,
    NetworkProfileCreate,
    NetworkProfileRead,
    NetworkProfileUpdate,
    ProfileLogsRead,
    RuntimeStatusRead,
)


router = APIRouter(prefix="/api/profiles", tags=["Network profiles"])


def _get_profile_or_404(profile_id: int) -> dict:
    profile = repository.get_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


def _record(profile_id: int | None, action: str, result: str, message: str) -> None:
    repository.add_action_log(profile_id, action, result, message)


def _raise_core_error(profile_id: int, action: str, error: CoreManagerError) -> None:
    repository.set_profile_status(profile_id, "error")
    _record(profile_id, action, "error", str(error))

    if isinstance(error, CoreUnavailableError):
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif isinstance(error, CoreValidationError):
        code = 422
    elif isinstance(error, CoreAlreadyRunningError):
        code = status.HTTP_409_CONFLICT
    else:
        code = status.HTTP_500_INTERNAL_SERVER_ERROR
    raise HTTPException(status_code=code, detail=str(error))


@router.get("", response_model=list[NetworkProfileRead])
def get_profiles() -> list[dict]:
    return repository.list_profiles()


@router.get("/{profile_id}", response_model=NetworkProfileRead)
def get_profile(profile_id: int) -> dict:
    return _get_profile_or_404(profile_id)


@router.post("", response_model=NetworkProfileRead, status_code=status.HTTP_201_CREATED)
def create_profile(data: NetworkProfileCreate) -> dict:
    profile = repository.create_profile(data)
    _record(profile["id"], "create", "success", "Profile created")
    return profile


@router.patch("/{profile_id}", response_model=NetworkProfileRead)
def update_profile(profile_id: int, data: NetworkProfileUpdate) -> dict:
    _get_profile_or_404(profile_id)
    if core_manager.get_runtime(profile_id).running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Deactivate the profile before updating it",
        )
    profile = repository.update_profile(profile_id, data)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    _record(profile_id, "update", "success", "Profile updated")
    return profile


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(profile_id: int) -> Response:
    if core_manager.get_runtime(profile_id).running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Deactivate the profile before deleting it",
        )
    deleted = repository.delete_profile(profile_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Profile not found")
    _record(profile_id, "delete", "success", "Profile deleted")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{profile_id}/validate", response_model=CoreValidationRead)
def validate_profile(profile_id: int) -> dict:
    profile = _get_profile_or_404(profile_id)
    try:
        result = core_manager.validate_profile(profile)
    except CoreManagerError as error:
        _raise_core_error(profile_id, "validate", error)
    _record(profile_id, "validate", "success", result.message)
    return {
        "profile_id": profile_id,
        "mode": get_core_mode(),
        "valid": result.valid,
        "message": result.message,
        "config_path": str(result.config_path) if result.config_path else None,
    }


@router.post("/{profile_id}/activate", response_model=NetworkProfileRead)
def activate_profile(profile_id: int) -> dict:
    profile = _get_profile_or_404(profile_id)
    try:
        runtime = core_manager.start_profile(profile)
    except CoreManagerError as error:
        _raise_core_error(profile_id, "activate", error)
    updated = repository.set_profile_status(profile_id, "active")
    _record(profile_id, "activate", "success", runtime.message)
    return updated


@router.post("/{profile_id}/deactivate", response_model=NetworkProfileRead)
def deactivate_profile(profile_id: int) -> dict:
    _get_profile_or_404(profile_id)
    try:
        runtime = core_manager.stop_profile(profile_id)
    except CoreManagerError as error:
        _raise_core_error(profile_id, "deactivate", error)
    updated = repository.set_profile_status(profile_id, "inactive")
    _record(profile_id, "deactivate", "success", runtime.message)
    return updated


@router.post("/{profile_id}/restart", response_model=NetworkProfileRead)
def restart_profile(profile_id: int) -> dict:
    profile = _get_profile_or_404(profile_id)
    try:
        runtime = core_manager.restart_profile(profile)
    except CoreManagerError as error:
        _raise_core_error(profile_id, "restart", error)
    updated = repository.set_profile_status(profile_id, "active")
    _record(profile_id, "restart", "success", runtime.message)
    return updated


@router.get("/{profile_id}/runtime", response_model=RuntimeStatusRead)
def get_runtime(profile_id: int) -> dict:
    _get_profile_or_404(profile_id)
    runtime = core_manager.get_runtime(profile_id)
    repository.set_profile_status(profile_id, runtime.status)
    return {
        "profile_id": profile_id,
        "mode": get_core_mode(),
        "status": runtime.status,
        "running": runtime.running,
        "pid": runtime.pid,
        "message": runtime.message,
    }


@router.get("/{profile_id}/logs", response_model=ProfileLogsRead)
def get_logs(
    profile_id: int,
    lines: int = Query(default=200, ge=1, le=1000),
) -> dict:
    _get_profile_or_404(profile_id)
    return {
        "profile_id": profile_id,
        "lines": core_manager.read_logs(profile_id, lines),
    }
