"""Pytest configuration and shared fixtures for NaijaBoost AI backend tests."""

from __future__ import annotations

import importlib
from collections.abc import Iterator

import pytest
from requests import Session


@pytest.fixture
def mocked_session() -> Iterator[tuple[Session, object]]:
    """Provide a requests session preconfigured with requests-mock."""

    session = Session()
    try:
        requests_mock = importlib.import_module("requests_mock")
    except ModuleNotFoundError as exc:  # pragma: no cover - runtime guard
        session.close()
        raise RuntimeError("Install requests-mock to use the mocked_session fixture") from exc

    mocker_cls = getattr(requests_mock, "Mocker")

    with mocker_cls(session=session) as mocker:
        try:
            yield session, mocker
        finally:
            session.close()