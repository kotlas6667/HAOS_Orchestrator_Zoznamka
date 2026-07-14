"""Config defaults for separated HA add-ons / local overrides."""

from __future__ import annotations

import importlib

import pytest


def test_orchestrator_defaults_point_to_addon_dns(monkeypatch):
    monkeypatch.delenv("ELITEDATE_BOT_URL", raising=False)
    monkeypatch.delenv("TINDER_BOT_URL", raising=False)
    import app.config as config

    importlib.reload(config)
    assert config.settings.elitedate_bot_url == "http://haos_elitedate:8600"
    assert config.settings.tinder_bot_url == "http://haos_tinder:8601"


def test_orchestrator_env_override_localhost(monkeypatch):
    monkeypatch.setenv("ELITEDATE_BOT_URL", "http://127.0.0.1:8600")
    monkeypatch.setenv("TINDER_BOT_URL", "http://127.0.0.1:8601")
    import app.config as config

    importlib.reload(config)
    assert config.settings.elitedate_bot_url == "http://127.0.0.1:8600"
    assert config.settings.tinder_bot_url == "http://127.0.0.1:8601"


def test_elitedate_bot_listens_on_all_interfaces_by_default(monkeypatch):
    for key in ("BOT_HOST", "BOT_PORT", "ORCHESTRATOR_URL"):
        monkeypatch.delenv(key, raising=False)
    import elitedate_bot.config as config

    importlib.reload(config)
    assert config.settings.bot_host == "0.0.0.0"
    assert config.settings.bot_port == 8600
    assert config.settings.orchestrator_url == "http://haos_orchestrator:8000"


def test_tinder_bot_listens_on_all_interfaces_by_default(monkeypatch):
    for key in (
        "TINDER_BOT_HOST",
        "TINDER_BOT_PORT",
        "ORCHESTRATOR_URL",
        "TINDER_HEADLESS",
        "TINDER_POLL_ENABLED",
    ):
        monkeypatch.delenv(key, raising=False)
    import tinder_bot.config as config

    importlib.reload(config)
    assert config.settings.bot_host == "0.0.0.0"
    assert config.settings.bot_port == 8601
    assert config.settings.orchestrator_url == "http://haos_orchestrator:8000"


@pytest.mark.parametrize(
    ("env", "value"),
    [
        ("ELITEDATE_AUTO_SEND", "true"),
        ("ELITEDATE_AUTO_SEND", "false"),
        ("TINDER_AUTO_SEND", "true"),
        ("TINDER_AUTO_SEND", "false"),
    ],
)
def test_auto_send_flags(monkeypatch, env, value):
    monkeypatch.setenv(env, value)
    import app.config as config

    importlib.reload(config)
    if env.startswith("ELITEDATE"):
        assert config.settings.elitedate_auto_send is (value == "true")
    else:
        assert config.settings.tinder_auto_send is (value == "true")
