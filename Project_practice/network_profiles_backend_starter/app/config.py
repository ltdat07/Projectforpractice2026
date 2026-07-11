import os
from pathlib import Path
from typing import Literal


BASE_DIR = Path(__file__).resolve().parent.parent


def get_core_mode() -> Literal["demo", "xray"]:
    """Return the selected network core mode.

    demo: API works without starting an external process.
    xray: API validates and controls a real Xray Core process.
    """
    mode = os.getenv("NETWORK_CORE_MODE", "demo").strip().lower()
    if mode not in {"demo", "xray"}:
        raise ValueError("NETWORK_CORE_MODE must be 'demo' or 'xray'")
    return mode  # type: ignore[return-value]


def get_xray_executable() -> Path:
    default_name = "xray.exe" if os.name == "nt" else "xray"
    default_path = BASE_DIR / "xray" / default_name
    configured = Path(os.getenv("XRAY_EXECUTABLE", str(default_path))).expanduser()
    if not configured.is_absolute():
        configured = BASE_DIR / configured
    return configured.resolve()


def get_runtime_dir() -> Path:
    configured = Path(os.getenv("RUNTIME_DIR", str(BASE_DIR / "runtime"))).expanduser()
    if not configured.is_absolute():
        configured = BASE_DIR / configured
    return configured.resolve()


def get_config_dir() -> Path:
    return get_runtime_dir() / "configs"


def get_log_dir() -> Path:
    return get_runtime_dir() / "logs"


def ensure_runtime_dirs() -> None:
    get_config_dir().mkdir(parents=True, exist_ok=True)
    get_log_dir().mkdir(parents=True, exist_ok=True)
