"""Packaging invariants — separated add-ons, slim orchestrator image."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_main_dockerfile_has_no_chromium():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    # Comment may mention Chromium; the image must not install/copy bots.
    assert "chromium-driver" not in text
    assert "apt-get install" in text
    assert "elitedate_bot/" not in text
    assert "tinder_bot/" not in text
    assert "COPY app/" in text


def test_main_run_sh_does_not_start_bots():
    text = (ROOT / "run.sh").read_text(encoding="utf-8")
    assert "python -m elitedate_bot.main" not in text
    assert "python -m tinder_bot.main" not in text
    assert "uvicorn app.main:app" in text


def test_elitedate_addon_manifest():
    cfg = json.loads((ROOT / "elitedate_bot" / "config.json").read_text(encoding="utf-8"))
    assert cfg["slug"] == "haos_elitedate"
    assert "8600/tcp" in cfg["ports"]
    assert "chromium" in (ROOT / "elitedate_bot" / "Dockerfile").read_text(encoding="utf-8").lower()


def test_tinder_addon_manifest():
    cfg = json.loads((ROOT / "tinder_bot" / "config.json").read_text(encoding="utf-8"))
    assert cfg["slug"] == "haos_tinder"
    assert "8601/tcp" in cfg["ports"]
    assert "6080/tcp" in cfg["ports"]
    assert "tinder_headless" in cfg["options"]
    assert "tinder_headless" in cfg["schema"]
    assert "orchestrator_url" in cfg["schema"]
    assert (ROOT / "tinder_bot" / "translations" / "sk.yaml").is_file()
    assert "chromium" in (ROOT / "tinder_bot" / "Dockerfile").read_text(encoding="utf-8").lower()
    run_sh = (ROOT / "tinder_bot" / "run.sh").read_text(encoding="utf-8")
    assert "options.json" in run_sh
    assert "apply_addon_options" in run_sh


def test_orchestrator_manifest_no_shm_requirement():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    assert cfg["slug"] == "haos_orchestrator"
    assert "shm_size" not in cfg


def test_bot_run_scripts_are_supervised():
    for bot in ("elitedate_bot", "tinder_bot"):
        text = (ROOT / bot / "run.sh").read_text(encoding="utf-8")
        assert "max_restarts" in text
        assert "python -m" in text
