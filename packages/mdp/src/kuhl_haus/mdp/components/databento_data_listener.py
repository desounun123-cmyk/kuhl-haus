"""Databento adapter that mimics the Massive WebSocket listener interface.

Used as a fallback when the primary Massive/Polygon.io WebSocket is
unavailable. Translates Databento's binary DBN feed and schema-based
subscription model into the Massive SDK message objects (EquityTrade,
EquityQuote, EquityAgg) expected by the rest of the kuhl-haus pipeline,
so no downstream component (serde, queue resolver, analyzers) needs to
change.

Key translations performed here:

* Subscription syntax — Massive ``"T.AAPL"`` / ``"Q.*"`` / ``"A.*"`` is
  parsed into a Databento schema (``trades``, ``mbp-1``, ``ohlcv-1m``)
  plus a symbol list (or ``ALL_SYMBOLS`` for wildcards).
* Timestamps — Databento delivers nanoseconds since epoch; the Massive
  models use milliseconds. Conversion is done at parse time.
* Message shape — DBN ``TradeMsg`` / ``MBP1Msg`` / ``OHLCVMsg`` are
  packed into the same kwargs the Massive SDK constructors accept.
* Auth & connect — Databento uses an API key on the ``Live`` client and
  an explicit ``start()`` call; the adapter exposes the same async
  ``start()`` / ``stop()`` / ``restart()`` lifecycle as the Massive
  listener.

LULD halts are not available on Databento equity feeds; subscriptions
beginning with ``LULD.`` are ignored with a warning.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, List, Optional, Union

try:  # Optional dependency; only required when the fallback is enabled.
    import databento as db
    from databento_dbn import OHLCVMsg, MBP1Msg, TradeMsg
    _DATABENTO_AVAILABLE = True
except ImportError:  # pragma: no cover - import guard
    db = None
    OHLCVMsg = MBP1Msg = TradeMsg = None  # type: ignore[assignment]
    _DATABENTO_AVAILABLE = False

from massive.websocket.models import (
    EquityAgg,
    EquityQuote,
    EquityTrade,
    EventType,
    WebSocketMessage,
)


# ---------------------------------------------------------------------------
# Subscription parsing
# ---------------------------------------------------------------------------

# Mapping from the Massive subscription prefix to the Databento schema.
_PREFIX_TO_SCHEMA = {
    "T": "trades",     # tick-level executions
    "Q": "mbp-1",      # top-of-book quotes (bid/ask)
    "A": "ohlcv-1s",   # per-second aggregate (closest to Massive "A.*")
    "AM": "ohlcv-1m",  # per-minute aggregate
}

# Subscription prefixes that have no Databento equivalent. We log and skip.
_UNSUPPORTED_PREFIXES = {"LULD"}


def _parse_subscriptions(subs: List[str]) -> dict[str, list[str]]:
    """Group Massive subscription strings by Databento schema.

    ``"T.AAPL"`` -> ``{"trades": ["AAPL"]}``
    ``"T.*"``    -> ``{"trades": ["ALL_SYMBOLS"]}``
    """
    grouped: dict[str, set[str]] = {}
    for raw in subs:
        if "." not in raw:
            continue
        prefix, symbol = raw.split(".", 1)
        prefix = prefix.upper()
        if prefix in _UNSUPPORTED_PREFIXES:
            logging.getLogger(__name__).warning(
                "Databento has no equivalent for %r subscription; ignoring", raw
            )
            continue
        schema = _PREFIX_TO_SCHEMA.get(prefix)
        if schema is None:
            continue
        grouped.setdefault(schema, set()).add(
            "ALL_SYMBOLS" if symbol == "*" else symbol.upper()
        )
    return {k: sorted(v) for k, v in grouped.items()}


# ---------------------------------------------------------------------------
# Message translation
# ---------------------------------------------------------------------------

def _ns_to_ms(ts_ns: int) -> int:
    """Convert Databento nanosecond timestamp to Massive millisecond timestamp."""
    return int(ts_ns // 1_000_000)


def _price_to_float(px: int) -> float:
    """Databento fixed-point price (1e-9 units) -> float dollars."""
    return px / 1_000_000_000.0


def _symbol_for(record) -> str:
    """Best-effort symbol extraction from a Databento record.

    Databento records carry an instrument_id; the canonical ticker is
    attached via ``record.pretty_ts_*`` helpers only when the Live client
    has symbol mappings. We fall back to the raw instrument_id as string.
    """
    return getattr(record, "symbol", None) or str(getattr(record, "instrument_id", ""))


def _record_to_massive(record) -> Optional[WebSocketMessage]:
    """Convert a single DBN record into the matching Massive SDK object."""
    if TradeMsg is not None and isinstance(record, TradeMsg):
        return EquityTrade(
            event_type=EventType.EquityTrade.value,
            symbol=_symbol_for(record),
            exchange=getattr(record, "publisher_id", 0),
            id=str(getattr(record, "sequence", "")),
            tape=0,
            price=_price_to_float(record.price),
            size=int(record.size),
            conditions=[],
            timestamp=_ns_to_ms(record.ts_event),
            sequence_number=int(getattr(record, "sequence", 0)),
            trf_id=0,
            trf_timestamp=0,
        )

    if MBP1Msg is not None and isinstance(record, MBP1Msg):
        # MBP-1 carries top-of-book in record.levels[0].
        level = record.levels[0] if record.levels else None
        bid_price = _price_to_float(level.bid_px) if level else 0.0
        ask_price = _price_to_float(level.ask_px) if level else 0.0
        bid_size = int(level.bid_sz) if level else 0
        ask_size = int(level.ask_sz) if level else 0
        return EquityQuote(
            event_type=EventType.EquityQuote.value,
            symbol=_symbol_for(record),
            bid_exchange_id=getattr(record, "publisher_id", 0),
            bid_price=bid_price,
            bid_size=bid_size,
            ask_exchange_id=getattr(record, "publisher_id", 0),
            ask_price=ask_price,
            ask_size=ask_size,
            condition=0,
            indicators=[],
            timestamp=_ns_to_ms(record.ts_event),
            sequence_number=int(getattr(record, "sequence", 0)),
            tape=0,
        )

    if OHLCVMsg is not None and isinstance(record, OHLCVMsg):
        return EquityAgg(
            event_type=EventType.EquityAgg.value,
            symbol=_symbol_for(record),
            volume=int(record.volume),
            accumulated_volume=int(record.volume),
            official_open_price=_price_to_float(record.open),
            vwap=0.0,
            open=_price_to_float(record.open),
            close=_price_to_float(record.close),
            high=_price_to_float(record.high),
            low=_price_to_float(record.low),
            aggregate_vwap=0.0,
            average_size=0,
            start_timestamp=_ns_to_ms(record.ts_event),
            end_timestamp=_ns_to_ms(record.ts_event),
            otc=False,
        )

    return None


# ---------------------------------------------------------------------------
# Listener
# ---------------------------------------------------------------------------

class DatabentoDataListener:
    """Drop-in replacement for ``MassiveDataListener`` backed by Databento.

    Exposes the same start/stop/restart API and ``connection_status`` dict
    so that the MDL server (and the :class:`FallbackDataListener`) can
    swap implementations without other changes.
    """

    def __init__(
        self,
        message_handler: Union[
            Callable[[List[WebSocketMessage]], Awaitable],
            Callable[[Union[str, bytes]], Awaitable],
        ],
        api_key: str,
        subscriptions: List[str],
        dataset: str = "XNAS.ITCH",
        max_reconnects: Optional[int] = 5,
        **kwargs,
    ):
        if not _DATABENTO_AVAILABLE:
            raise RuntimeError(
                "The 'databento' package is not installed; install it to use "
                "the Databento fallback listener."
            )
        self.logger = logging.getLogger(__name__)
        self.message_handler = message_handler
        self.api_key = api_key
        self.dataset = dataset
        self._subscriptions = subscriptions
        self.max_reconnects = max_reconnects
        self._client: Optional["db.Live"] = None
        self._task: Optional[asyncio.Task] = None
        self.connection_status: dict = {
            "connected": False,
            "healthy": False,
            "provider": "databento",
            "dataset": dataset,
            "reconnects": 0,
            "subscriptions": list(subscriptions),
        }

    # -- public state ------------------------------------------------------

    @property
    def subscriptions(self) -> List[str]:
        return self._subscriptions

    @subscriptions.setter
    def subscriptions(self, value: List[str]) -> None:
        self._subscriptions = list(value)
        self.connection_status["subscriptions"] = list(value)
        if self.connection_status.get("connected"):
            asyncio.create_task(self.restart())

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        """Open a Databento Live session and begin streaming."""
        try:
            self.logger.info("Instantiating Databento Live client...")
            self._client = db.Live(key=self.api_key)
            for schema, symbols in _parse_subscriptions(self._subscriptions).items():
                self.logger.info(
                    "Subscribing dataset=%s schema=%s symbols=%s",
                    self.dataset, schema, symbols,
                )
                self._client.subscribe(
                    dataset=self.dataset,
                    schema=schema,
                    symbols=symbols if symbols != ["ALL_SYMBOLS"] else "ALL_SYMBOLS",
                )
            self.connection_status["connected"] = True
            self.connection_status["healthy"] = True
            self._task = asyncio.create_task(self._consume())
        except Exception as exc:  # pragma: no cover - network/auth errors
            self.logger.error("Error starting Databento client: %s", exc)
            self.connection_status["healthy"] = False
            await self.stop()
            raise

    async def stop(self) -> None:
        """Close the Databento session and cancel the consumer task."""
        try:
            if self._task is not None:
                self._task.cancel()
                await asyncio.sleep(0)
            if self._client is not None:
                stop_fn = getattr(self._client, "stop", None)
                if callable(stop_fn):
                    try:
                        stop_fn()
                    except Exception as exc:  # pragma: no cover
                        self.logger.warning("Databento stop() raised: %s", exc)
        finally:
            self._task = None
            self._client = None
            self.connection_status["connected"] = False

    async def restart(self) -> None:
        await self.stop()
        await asyncio.sleep(1)
        await self.start()

    # -- streaming loop ----------------------------------------------------

    async def _consume(self) -> None:
        """Iterate the Databento async stream and forward translated messages."""
        assert self._client is not None
        try:
            self._client.start()
            async for record in self._client:
                converted = _record_to_massive(record)
                if converted is None:
                    continue
                try:
                    await self.message_handler([converted])
                except Exception as exc:  # downstream errors must not kill the loop
                    self.logger.error("message_handler raised: %s", exc, exc_info=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.connection_status["healthy"] = False
            self.connection_status["connected"] = False
            self.logger.error(
                "Databento stream terminated: %s", exc, exc_info=True
            )
