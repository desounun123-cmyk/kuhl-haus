"""Unit tests for the Databento adapter.

The tests exercise the pure-Python translation helpers
(_parse_subscriptions, _record_to_massive) without requiring a network
connection to Databento. The Live client itself is mocked.
"""
from __future__ import annotations

import asyncio
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from kuhl_haus.mdp.components import databento_data_listener as ddl


def test_parse_subscriptions_groups_by_schema():
    parsed = ddl._parse_subscriptions(["T.AAPL", "T.MSFT", "Q.AAPL", "A.*"])
    assert parsed["trades"] == ["AAPL", "MSFT"]
    assert parsed["mbp-1"] == ["AAPL"]
    assert parsed["ohlcv-1s"] == ["ALL_SYMBOLS"]


def test_parse_subscriptions_skips_unsupported_prefixes(caplog):
    with caplog.at_level("WARNING"):
        parsed = ddl._parse_subscriptions(["LULD.*"])
    assert parsed == {}
    assert any("LULD" in r.message for r in caplog.records)


def test_ns_to_ms_truncates_correctly():
    assert ddl._ns_to_ms(1_700_000_000_123_456_789) == 1_700_000_000_123


def test_price_conversion_uses_1e9_fixed_point():
    assert ddl._price_to_float(150_000_000_000) == pytest.approx(150.0)


def _fake_trade(symbol="AAPL", ts_event=1_700_000_000_000_000_000, price=15_000_000_000, size=10):
    rec = types.SimpleNamespace()
    rec.symbol = symbol
    rec.ts_event = ts_event
    rec.price = price
    rec.size = size
    rec.sequence = 42
    rec.publisher_id = 7
    rec.instrument_id = 999
    return rec


def test_record_to_massive_returns_none_for_unknown(monkeypatch):
    # Trade-like duck typing but isinstance() check uses TradeMsg type, so a
    # SimpleNamespace will not match any branch and should return None.
    monkeypatch.setattr(ddl, "TradeMsg", type("X", (), {}))
    monkeypatch.setattr(ddl, "MBP1Msg", type("Y", (), {}))
    monkeypatch.setattr(ddl, "OHLCVMsg", type("Z", (), {}))
    assert ddl._record_to_massive(object()) is None


def test_record_to_massive_translates_trade(monkeypatch):
    """A record that is an instance of TradeMsg is translated to EquityTrade."""

    class FakeTradeMsg(types.SimpleNamespace):
        pass

    monkeypatch.setattr(ddl, "TradeMsg", FakeTradeMsg)
    rec = FakeTradeMsg(
        symbol="AAPL",
        ts_event=1_700_000_000_000_000_000,
        price=15_000_000_000,
        size=10,
        sequence=42,
        publisher_id=7,
        instrument_id=999,
    )
    out = ddl._record_to_massive(rec)
    assert out is not None
    assert out.symbol == "AAPL"
    assert out.price == pytest.approx(15.0)
    assert out.size == 10
    assert out.timestamp == 1_700_000_000_000  # ns -> ms


@pytest.mark.asyncio
async def test_listener_requires_databento_package(monkeypatch):
    monkeypatch.setattr(ddl, "_DATABENTO_AVAILABLE", False)
    with pytest.raises(RuntimeError, match="not installed"):
        ddl.DatabentoDataListener(
            message_handler=AsyncMock(),
            api_key="x",
            subscriptions=["T.AAPL"],
        )


@pytest.mark.asyncio
async def test_listener_start_subscribes_each_schema(monkeypatch):
    """start() should call client.subscribe() once per parsed schema."""

    monkeypatch.setattr(ddl, "_DATABENTO_AVAILABLE", True)

    fake_client = MagicMock()
    fake_client.subscribe = MagicMock()
    fake_client.start = MagicMock()

    async def _iter(self):
        if False:  # pragma: no cover - generator placeholder
            yield None
        return

    fake_client.__aiter__ = lambda self: _iter(self)

    fake_db = types.SimpleNamespace(Live=MagicMock(return_value=fake_client))
    monkeypatch.setattr(ddl, "db", fake_db)

    listener = ddl.DatabentoDataListener(
        message_handler=AsyncMock(),
        api_key="key",
        subscriptions=["T.AAPL", "Q.MSFT"],
    )
    await listener.start()
    # Give the consumer task a chance to start so we can cancel cleanly.
    await asyncio.sleep(0)
    await listener.stop()

    schemas_called = {call.kwargs["schema"] for call in fake_client.subscribe.call_args_list}
    assert schemas_called == {"trades", "mbp-1"}
    assert listener.connection_status["provider"] == "databento"
