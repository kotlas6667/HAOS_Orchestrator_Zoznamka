"""Shared fixtures for HAOS / dating-bot tests."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

import pytest


@pytest.fixture
def fake_driver() -> MagicMock:
    driver = MagicMock()
    type(driver).current_url = PropertyMock(return_value="https://example.com/")
    return driver


@pytest.fixture
def dead_driver() -> MagicMock:
    driver = MagicMock()
    type(driver).current_url = PropertyMock(side_effect=Exception("invalid session id"))
    return driver
