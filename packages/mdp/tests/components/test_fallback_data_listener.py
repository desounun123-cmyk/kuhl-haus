"""Unit tests for the FallbackDataListener wrapper."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kuhl_haus.mdp.components import fallback_data_listener as fdl


def _build(listener_kwargs: dict | None = None, **overrides):
    """Construct a FallbackDataListener with the Massive primary mocked out."""
    kwargs = dict(
        message_handler=AsyncMock(),
        api_key="massive-key",
        feed="real_time",
        market="stocks",
        subscriptions=["T.AAPL"],
        databento_api_key="db-key",
    )
    kwargs.update(overrides)
    with patch.object(fdl, "MassiveDataListener") as primary_cls:
        primary = MagicMock()
        primary.start = AsyncMock()
        primary.stop = AsyncMock()
        primary.connection_status = {"connected": True, "healthy": True}
        primary.feed = "real_time"
        primary.market = "stocks"
        primary.subscriptions = ["T.AAPL"]
        primary_cls.return_value = primary
        listener = fdl.FallbackDataListener(**kwargs)
    return listener, primary


@pytest.mark.asyncio
async def test_start_uses_primary_by_default():
    listener, primary = _build()
    await listener.start()
    primary.start.assert_awaited_once()
    assert listener._active == "massive"


@pytest.mark.asyncio
async def test_start_falls_back_to_databento_on_primary_failure():
    listener, primary = _build()
    primary.start.side_effect = RuntimeError("massive down")

    fake_fallback = MagicMock()
    fake_fallback.start = AsyncMock()
    fake_fallback.stop = AsyncMock()
    fake_fallback.connection_status = {"connected": True, "healthy": True, "provider": "databento"}

    with patch(
        "kuhl_haus.mdp.components.databento_data_listener.DatabentoDataListener",
        return_value=fake_fallback,
    ):
        await listener.start()

    assert listener._active == "databento"
    fake_fallback.start.assert_awaited_once()
    # A recovery task should have been scheduled.
    assert listener._recovery_task is not None
    listener._recovery_task.cancel()


@pytest.mark.asyncio
async def test_no_fallback_when_databento_key_missing():
    listener, primary = _build(databento_api_key=None)
    primary.start.side_effect = RuntimeError("massive down")

    await listener.start()

    # Without a Databento key we stay on massive but mark unhealthy elsewhere.
    assert listener._active == "massive"
    assert listener._fallback is None


@pytest.mark.asyncio
async def test_subscriptions_setter_propagates_to_both():
    listener, primary = _build()

    fake_fallback = MagicMock()
    fake_fallback.subscriptions = []
    listener._fallback = fake_fallback

    listener.subscriptions = ["T.MSFT", "Q.MSFT"]

    assert primary.subscriptions == ["T.MSFT", "Q.MSFT"]
    assert fake_fallback.subscriptions == ["T.MSFT", "Q.MSFT"]
    assert listener.subscriptions == ["T.MSFT", "Q.MSFT"]


@pytest.mark.asyncio
async def test_connection_status_includes_active_provider():
    listener, _ = _build()
    status = listener.connection_status
    assert status["active_provider"] == "massive"
    assert status["fallback_available"] is True


@pytest.mark.asyncio
async def test_stop_cancels_recovery_task():
    listener, primary = _build()

    async def _noop():
        await asyncio.sleep(60)

    listener._recovery_task = asyncio.create_task(_noop())
    await listener.stop()
    assert listener._recovery_task is None
    primary.stop.assert_awaited()
