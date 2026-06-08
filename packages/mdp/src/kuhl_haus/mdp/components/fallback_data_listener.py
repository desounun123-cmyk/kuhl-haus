"""Massive-primary / Databento-fallback market-data listener.

Wraps :class:`MassiveDataListener` and (optionally) a Databento adapter
behind the same public surface as the original Massive listener. The
MDL server can therefore use this class as a drop-in replacement and
gain automatic failover without further changes.

Behaviour
---------

* ``start()`` always tries Massive first. If Massive raises during
  startup, or if Massive disconnects and burns through ``max_reconnects``
  retries, the wrapper transparently swaps to Databento (provided a
  Databento API key was supplied at construction time).
* While running on Databento the wrapper schedules a periodic recovery
  task that re-attempts Massive every ``recovery_interval_seconds`` and
  switches back if Massive comes online.
* If no Databento key is configured the wrapper behaves exactly like
  ``MassiveDataListener`` (no fallback, no recovery task).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, List, Optional, Union

from massive.websocket import Feed, Market, WebSocketMessage

from kuhl_haus.mdp.components.massive_data_listener import MassiveDataListener


class FallbackDataListener:
    """Coordinate a primary Massive listener and a Databento fallback."""

    def __init__(
        self,
        message_handler: Union[
            Callable[[List[WebSocketMessage]], Awaitable],
            Callable[[Union[str, bytes]], Awaitable],
        ],
        api_key: str,
        feed: Feed,
        market: Market,
        subscriptions: List[str],
        raw: bool = False,
        verbose: bool = False,
        max_reconnects: Optional[int] = 5,
        secure: bool = True,
        databento_api_key: Optional[str] = None,
        databento_dataset: str = "XNAS.ITCH",
        recovery_interval_seconds: int = 300,
        **kwargs,
    ):
        self.logger = logging.getLogger(__name__)
        self._message_handler = message_handler
        self._subscriptions = list(subscriptions)
        self._databento_api_key = databento_api_key
        self._databento_dataset = databento_dataset
        self._recovery_interval = recovery_interval_seconds
        self._active = "massive"
        self._recovery_task: Optional[asyncio.Task] = None

        # Primary listener — always constructed.
        self._primary = MassiveDataListener(
            message_handler=message_handler,
            api_key=api_key,
            feed=feed,
            market=market,
            subscriptions=subscriptions,
            raw=raw,
            verbose=verbose,
            max_reconnects=max_reconnects,
            secure=secure,
            **kwargs,
        )

        # Fallback is lazily instantiated on first failover so we don't
        # import the databento package unless it's actually needed.
        self._fallback: Optional["object"] = None

    # ------------------------------------------------------------------
    # Public surface mirroring MassiveDataListener
    # ------------------------------------------------------------------

    @property
    def connection_status(self) -> dict:
        status = dict(self._active_listener().connection_status)
        status["active_provider"] = self._active
        status["fallback_available"] = bool(self._databento_api_key)
        return status

    @property
    def feed(self) -> Feed:
        return self._primary.feed

    @feed.setter
    def feed(self, value: Feed) -> None:
        self._primary.feed = value

    @property
    def market(self) -> Market:
        return self._primary.market

    @market.setter
    def market(self, value: Market) -> None:
        self._primary.market = value

    @property
    def subscriptions(self) -> List[str]:
        return self._subscriptions

    @subscriptions.setter
    def subscriptions(self, value: List[str]) -> None:
        self._subscriptions = list(value)
        self._primary.subscriptions = list(value)
        if self._fallback is not None:
            self._fallback.subscriptions = list(value)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        try:
            await self._primary.start()
            self._active = "massive"
            self.logger.info("Primary Massive listener started.")
        except Exception as exc:
            self.logger.error(
                "Massive start failed (%s); attempting Databento fallback.", exc
            )
            await self._activate_fallback()

    async def stop(self) -> None:
        await self._cancel_recovery()
        if self._active == "massive":
            await self._primary.stop()
        elif self._fallback is not None:
            await self._fallback.stop()

    async def restart(self) -> None:
        await self.stop()
        await asyncio.sleep(1)
        await self.start()

    # ------------------------------------------------------------------
    # Failover helpers
    # ------------------------------------------------------------------

    def _active_listener(self):
        if self._active == "databento" and self._fallback is not None:
            return self._fallback
        return self._primary

    async def _activate_fallback(self) -> None:
        if not self._databento_api_key:
            self.logger.error(
                "No Databento API key configured; cannot fall back. "
                "MDL will remain in an unhealthy state until Massive recovers."
            )
            return

        # Defer the import so we don't require the dependency unless needed.
        from kuhl_haus.mdp.components.databento_data_listener import (
            DatabentoDataListener,
        )

        try:
            await self._primary.stop()
        except Exception as exc:  # pragma: no cover
            self.logger.warning("Error stopping Massive primary: %s", exc)

        if self._fallback is None:
            self._fallback = DatabentoDataListener(
                message_handler=self._message_handler,
                api_key=self._databento_api_key,
                subscriptions=self._subscriptions,
                dataset=self._databento_dataset,
            )

        try:
            await self._fallback.start()
            self._active = "databento"
            self.logger.warning(
                "Switched to Databento fallback (dataset=%s).",
                self._databento_dataset,
            )
            self._schedule_recovery()
        except Exception as exc:
            self.logger.error("Databento fallback also failed: %s", exc)
            self._active = "unhealthy"

    def _schedule_recovery(self) -> None:
        if self._recovery_task and not self._recovery_task.done():
            return
        self._recovery_task = asyncio.create_task(self._recovery_loop())

    async def _cancel_recovery(self) -> None:
        if self._recovery_task is not None:
            self._recovery_task.cancel()
            try:
                await self._recovery_task
            except (asyncio.CancelledError, Exception):
                pass
            self._recovery_task = None

    async def _recovery_loop(self) -> None:
        """Periodically attempt to switch back to the primary Massive feed."""
        while self._active == "databento":
            await asyncio.sleep(self._recovery_interval)
            self.logger.info("Probing Massive primary for recovery...")
            try:
                await self._primary.start()
            except Exception as exc:
                self.logger.info("Massive still unavailable: %s", exc)
                continue
            # Primary came back — stop the fallback and switch over.
            if self._fallback is not None:
                try:
                    await self._fallback.stop()
                except Exception as exc:  # pragma: no cover
                    self.logger.warning("Error stopping Databento fallback: %s", exc)
            self._active = "massive"
            self.logger.warning("Massive primary recovered; failback complete.")
            return
