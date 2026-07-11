import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import (
    ensure_runtime_dirs,
    get_config_dir,
    get_core_mode,
    get_log_dir,
    get_xray_executable,
)


class CoreManagerError(RuntimeError):
    pass


class CoreUnavailableError(CoreManagerError):
    pass


class CoreValidationError(CoreManagerError):
    pass


class CoreAlreadyRunningError(CoreManagerError):
    pass


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    message: str
    config_path: Path | None


@dataclass(frozen=True)
class RuntimeInfo:
    running: bool
    pid: int | None
    status: str
    message: str


class XrayCoreManager:
    """Manages one Xray process per profile inside the current backend process."""

    def __init__(self) -> None:
        self._processes: dict[int, subprocess.Popen[Any]] = {}
        self._demo_active: set[int] = set()
        self._lock = threading.RLock()

    def _config_path(self, profile_id: int) -> Path:
        ensure_runtime_dirs()
        return get_config_dir() / f"profile_{profile_id}.json"

    def _log_path(self, profile_id: int) -> Path:
        ensure_runtime_dirs()
        return get_log_dir() / f"profile_{profile_id}.log"

    def _write_config(self, profile: dict[str, Any]) -> Path:
        config = profile.get("config")
        if not isinstance(config, dict) or not config:
            raise CoreValidationError(
                "Profile config must contain a non-empty complete Xray JSON configuration"
            )

        path = self._config_path(profile["id"])
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)
        return path

    @staticmethod
    def _clean_output(*values: str | None) -> str:
        parts = [value.strip() for value in values if value and value.strip()]
        return "\n".join(parts)[-4000:] or "No output"

    def validate_profile(self, profile: dict[str, Any]) -> ValidationResult:
        config_path = self._write_config(profile)
        mode = get_core_mode()

        if mode == "demo":
            return ValidationResult(
                valid=True,
                message="Demo mode: JSON configuration was written successfully",
                config_path=config_path,
            )

        executable = get_xray_executable()
        if not executable.is_file():
            raise CoreUnavailableError(
                f"Xray executable was not found: {executable}. "
                "Set XRAY_EXECUTABLE or place xray.exe in the xray folder."
            )

        try:
            completed = subprocess.run(
                [str(executable), "run", "-test", "-c", str(config_path)],
                cwd=executable.parent,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CoreValidationError("Xray configuration validation timed out") from exc
        except OSError as exc:
            raise CoreUnavailableError(f"Could not start Xray validator: {exc}") from exc

        output = self._clean_output(completed.stdout, completed.stderr)
        if completed.returncode != 0:
            raise CoreValidationError(f"Xray rejected the configuration:\n{output}")

        return ValidationResult(True, output, config_path)

    def start_profile(self, profile: dict[str, Any]) -> RuntimeInfo:
        profile_id = int(profile["id"])
        with self._lock:
            if get_core_mode() == "demo":
                if profile_id in self._demo_active:
                    raise CoreAlreadyRunningError("This profile is already active")
                validation = self.validate_profile(profile)
                self._demo_active.add(profile_id)
                return RuntimeInfo(
                    running=True,
                    pid=None,
                    status="active",
                    message=validation.message,
                )

            current = self._processes.get(profile_id)
            if current is not None and current.poll() is None:
                raise CoreAlreadyRunningError("This profile is already active")

            validation = self.validate_profile(profile)

            executable = get_xray_executable()
            log_path = self._log_path(profile_id)
            creationflags = 0
            if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
                creationflags = subprocess.CREATE_NO_WINDOW

            try:
                with log_path.open("a", encoding="utf-8") as log_file:
                    log_file.write("\n--- Xray start requested ---\n")
                    log_file.flush()
                    process = subprocess.Popen(
                        [
                            str(executable),
                            "run",
                            "-c",
                            str(validation.config_path),
                        ],
                        cwd=executable.parent,
                        stdout=log_file,
                        stderr=subprocess.STDOUT,
                        text=True,
                        creationflags=creationflags,
                    )
            except OSError as exc:
                raise CoreUnavailableError(f"Could not start Xray: {exc}") from exc

            time.sleep(0.25)
            return_code = process.poll()
            if return_code is not None:
                message = "Xray stopped immediately after start"
                log_tail = "\n".join(self.read_logs(profile_id, 30))
                if log_tail:
                    message += f":\n{log_tail}"
                raise CoreManagerError(message)

            self._processes[profile_id] = process
            return RuntimeInfo(
                running=True,
                pid=process.pid,
                status="active",
                message="Xray process started",
            )

    def stop_profile(self, profile_id: int) -> RuntimeInfo:
        with self._lock:
            if get_core_mode() == "demo":
                self._demo_active.discard(profile_id)
                return RuntimeInfo(False, None, "inactive", "Demo profile deactivated")

            process = self._processes.pop(profile_id, None)

            if process is None or process.poll() is not None:
                return RuntimeInfo(False, None, "inactive", "Xray process is not running")

            pid = process.pid
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)

            return RuntimeInfo(False, pid, "inactive", "Xray process stopped")

    def restart_profile(self, profile: dict[str, Any]) -> RuntimeInfo:
        self.stop_profile(int(profile["id"]))
        return self.start_profile(profile)

    def get_runtime(self, profile_id: int) -> RuntimeInfo:
        if get_core_mode() == "demo":
            running = profile_id in self._demo_active
            return RuntimeInfo(
                running=running,
                pid=None,
                status="active" if running else "inactive",
                message=(
                    "Demo profile is active"
                    if running
                    else "Demo profile is inactive"
                ),
            )

        with self._lock:
            process = self._processes.get(profile_id)
            if process is None:
                return RuntimeInfo(False, None, "inactive", "Xray process is not running")
            return_code = process.poll()
            if return_code is None:
                return RuntimeInfo(True, process.pid, "active", "Xray process is running")
            self._processes.pop(profile_id, None)
            return RuntimeInfo(
                False,
                process.pid,
                "error",
                f"Xray process exited with code {return_code}",
            )

    def read_logs(self, profile_id: int, lines: int = 200) -> list[str]:
        safe_lines = max(1, min(lines, 1000))
        path = self._log_path(profile_id)
        if not path.exists():
            return []
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return content[-safe_lines:]

    def shutdown(self) -> None:
        with self._lock:
            self._demo_active.clear()
            profile_ids = list(self._processes)
        for profile_id in profile_ids:
            try:
                self.stop_profile(profile_id)
            except CoreManagerError:
                pass


core_manager = XrayCoreManager()
