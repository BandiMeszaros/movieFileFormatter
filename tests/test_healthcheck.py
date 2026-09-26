import os
import time

import pytest

from app import healthcheck, main


@pytest.fixture
def healthy(tmp_path, monkeypatch):
    for name in ("input", "output", "state"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(healthcheck.settings, "input_dir", str(tmp_path / "input"))
    monkeypatch.setattr(healthcheck.settings, "output_dir", str(tmp_path / "output"))
    monkeypatch.setattr(
        healthcheck.settings, "state_file", str(tmp_path / "state" / "processed.json")
    )
    monkeypatch.setattr(healthcheck.settings, "heartbeat_file", str(tmp_path / "heartbeat"))
    monkeypatch.setattr(healthcheck.settings, "heartbeat_max_age_seconds", 60)
    main.touch_heartbeat()
    return tmp_path


def test_healthy_after_heartbeat(healthy):
    assert healthcheck.check() == []
    assert healthcheck.main() == 0


def test_unhealthy_without_heartbeat(healthy):
    os.remove(healthy / "heartbeat")
    assert healthcheck.main() == 1


def test_unhealthy_when_heartbeat_is_stale(healthy):
    old = time.time() - 120
    os.utime(healthy / "heartbeat", (old, old))
    assert any("heartbeat" in p for p in healthcheck.check())


def test_unhealthy_when_mount_missing(healthy):
    os.rmdir(healthy / "output")
    assert any("MOVIE_OUTPUT" in p for p in healthcheck.check())
