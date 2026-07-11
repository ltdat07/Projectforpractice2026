import subprocess
from pathlib import Path

import pytest

from app.core_manager import (
    CoreManagerError,
    CoreUnavailableError,
    CoreValidationError,
    ValidationResult,
    XrayCoreManager,
)


PROFILE = {
    "id": 7,
    "config": {
        "inbounds": [],
        "outbounds": [{"protocol": "freedom"}],
    },
}


def configure_real_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    executable = tmp_path / "xray.exe"
    executable.write_bytes(b"fake")
    monkeypatch.setenv("NETWORK_CORE_MODE", "xray")
    monkeypatch.setenv("XRAY_EXECUTABLE", str(executable))
    monkeypatch.setenv("RUNTIME_DIR", str(tmp_path / "runtime"))
    return executable


def test_real_validation_builds_official_xray_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = configure_real_mode(tmp_path, monkeypatch)
    captured: dict = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, "Configuration OK", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    manager = XrayCoreManager()
    result = manager.validate_profile(PROFILE)

    assert result.valid is True
    assert result.config_path is not None and result.config_path.exists()
    assert captured["command"] == [
        str(executable),
        "run",
        "-test",
        "-c",
        str(result.config_path),
    ]
    assert captured["kwargs"]["timeout"] == 20


def test_real_validation_rejects_invalid_xray_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_real_mode(tmp_path, monkeypatch)

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 23, "", "invalid config")

    monkeypatch.setattr(subprocess, "run", fake_run)
    manager = XrayCoreManager()

    with pytest.raises(CoreValidationError, match="invalid config"):
        manager.validate_profile(PROFILE)


def test_real_mode_reports_missing_executable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NETWORK_CORE_MODE", "xray")
    monkeypatch.setenv("XRAY_EXECUTABLE", str(tmp_path / "missing-xray.exe"))
    monkeypatch.setenv("RUNTIME_DIR", str(tmp_path / "runtime"))

    with pytest.raises(CoreUnavailableError, match="was not found"):
        XrayCoreManager().validate_profile(PROFILE)


def test_real_start_status_and_stop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = configure_real_mode(tmp_path, monkeypatch)
    manager = XrayCoreManager()
    config_path = tmp_path / "runtime" / "configs" / "profile_7.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        manager,
        "validate_profile",
        lambda profile: ValidationResult(True, "ok", config_path),
    )

    captured: dict = {}

    class FakeProcess:
        pid = 4321

        def __init__(self):
            self.return_code = None
            self.terminated = False

        def poll(self):
            return self.return_code

        def terminate(self):
            self.terminated = True
            self.return_code = 0

        def wait(self, timeout=None):
            return self.return_code

        def kill(self):
            self.return_code = -9

    fake_process = FakeProcess()

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return fake_process

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr("app.core_manager.time.sleep", lambda _: None)

    started = manager.start_profile(PROFILE)
    assert started.running is True
    assert started.pid == 4321
    assert captured["command"] == [
        str(executable),
        "run",
        "-c",
        str(config_path),
    ]

    runtime = manager.get_runtime(7)
    assert runtime.running is True
    assert runtime.status == "active"

    stopped = manager.stop_profile(7)
    assert stopped.running is False
    assert stopped.status == "inactive"
    assert fake_process.terminated is True


def test_real_start_detects_immediate_process_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_real_mode(tmp_path, monkeypatch)
    manager = XrayCoreManager()
    config_path = tmp_path / "runtime" / "configs" / "profile_7.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        manager,
        "validate_profile",
        lambda profile: ValidationResult(True, "ok", config_path),
    )

    class ExitedProcess:
        pid = 9

        @staticmethod
        def poll():
            return 1

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: ExitedProcess())
    monkeypatch.setattr("app.core_manager.time.sleep", lambda _: None)

    with pytest.raises(CoreManagerError, match="stopped immediately"):
        manager.start_profile(PROFILE)
