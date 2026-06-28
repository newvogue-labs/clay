"""Tests for the FastAPI lifespan context (B1 + B3a + C2)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from asgi_lifespan import LifespanManager

import clay.api.lifespan as lifespan_module
from clay.api.main import app
from clay.scheduler.service import ClayScheduler
from clay.settings.scheduler import SchedulerSettings


@pytest.mark.anyio
async def test_lifespan_starts_scheduler_by_default() -> None:
    """Boot order: startup → yield → shutdown без ошибок, scheduler started.

    Default (``CLAY_SCHEDULER_ENABLED`` unset → ``True``): the
    ``ClayScheduler`` is constructed and its ``start()`` is called.
    ``app.state.scheduler`` is the live scheduler instance; on
    LifespanManager exit, ``shutdown(wait=True)`` runs and the
    scheduler walks to ``STOPPED``.

    Использует module-level ``app`` (``clay.api.main:app``) и **не**
    пересобирает service graph — A6 rule: один factory call, никаких
    параллельных hand-rolled bundle'ов. LifespanManager вызывает
    startup до ``async with`` и shutdown после ``__aexit__``;
    exception'ы из lifespan тела re-raise'ятся, поэтому «shutdown
    выполнилась» проверяется самим фактом прохождения теста.
    """
    async with LifespanManager(app):
        assert app.state.started_at is not None
        assert isinstance(app.state.scheduler, ClayScheduler)


@pytest.mark.anyio
async def test_lifespan_skips_scheduler_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``CLAY_SCHEDULER_ENABLED=false`` → ``app.state.scheduler is None``.

    B0 / B3a dev-mode path: uvicorn ``--reload``, multi-worker
    guards, etc. The scheduler is **not** constructed; no
    ``AsyncIOScheduler`` is started. ``app.state.started_at`` is
    still stamped (it's a lifespan marker, not a scheduler marker).
    """
    monkeypatch.setattr(
        lifespan_module,
        "scheduler_settings",
        SchedulerSettings(enabled=False),
    )
    async with LifespanManager(app):
        assert app.state.scheduler is None
        assert app.state.started_at is not None


@pytest.mark.anyio
async def test_lifespan_injects_http_client_before_scheduler_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C2 ordering: ``set_http_client`` fires BEFORE ``scheduler.start()``.

    The scheduler-job (``IngestionCycleJob``) reaches the client via
    the import-time ``MarketIngestionService`` singleton — if injection
    lagged ``start()``, the very first scheduler tick would fall
    through to the per-call else-branch and re-introduce HIGH-2.
    """
    calls: list[str] = []
    fake_client = MagicMock()
    fake_client.is_closed = False
    fake_client.aclose = MagicMock()

    monkeypatch.setattr(
        lifespan_module._market_ingestion_service,
        "set_http_client",
        lambda c: (
            calls.append("set_http_client")
            or lifespan_module._market_ingestion_service.__class__.set_http_client(
                lifespan_module._market_ingestion_service, c
            )
        ),
    )

    real_start = ClayScheduler.start

    def recording_start(self) -> None:
        calls.append("scheduler.start")
        real_start(self)

    monkeypatch.setattr(ClayScheduler, "start", recording_start)

    # Patch httpx.AsyncClient to return our fake (no real network).
    monkeypatch.setattr(
        lifespan_module.httpx, "AsyncClient", lambda **kwargs: fake_client
    )

    async with LifespanManager(app):
        pass

    # Order: set_http_client must precede scheduler.start.
    assert calls.index("set_http_client") < calls.index("scheduler.start")


@pytest.mark.anyio
async def test_lifespan_aclose_after_scheduler_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C2 MED-3: ``http_client.aclose()`` runs STRICTLY AFTER
    ``scheduler.shutdown(wait=True)``.

    If the order flips, in-flight ``IngestionCycleJob`` coroutines may
    use a closed client and surface as noisy ``ingestion.cycle_failed``
    audit events on every shutdown — making graceful shutdown look
    like a regression.
    """
    calls: list[str] = []
    fake_client = MagicMock()

    async def fake_aclose() -> None:
        calls.append("aclose")

    fake_client.aclose = fake_aclose
    fake_client.is_closed = False
    monkeypatch.setattr(
        lifespan_module.httpx, "AsyncClient", lambda **kwargs: fake_client
    )

    real_shutdown = ClayScheduler.shutdown

    def recording_shutdown(self, wait: bool = True) -> None:
        calls.append("scheduler.shutdown")
        real_shutdown(self, wait=wait)

    monkeypatch.setattr(ClayScheduler, "shutdown", recording_shutdown)

    async with LifespanManager(app):
        pass

    # Strict order: scheduler.shutdown precedes aclose.
    assert calls.index("scheduler.shutdown") < calls.index("aclose")


@pytest.mark.anyio
async def test_lifespan_initializes_http_client_none_before_try(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C2 boot-safety pin: ``http_client`` is bound to ``None`` before the
    ``try`` block, so a startup failure that happens BEFORE the
    ``AsyncClient(...)`` ctor (or inside it) does not leave the
    ``finally`` block referencing an undefined name — which would
    raise ``UnboundLocalError`` and mask the real startup error.
    """

    # Force an exception inside the startup body, AFTER app.state stamps
    # but BEFORE we would create the AsyncClient. Simplest trigger: make
    # ``set_http_client`` blow up on the very first call.
    def boom(_client) -> None:
        raise RuntimeError("synthetic startup failure (C2 pin)")

    monkeypatch.setattr(
        lifespan_module._market_ingestion_service, "set_http_client", boom
    )

    # The actual call path: lifespan calls ``set_http_client`` AFTER
    # creating the AsyncClient. So we need to fail on the AsyncClient
    # ctor itself to exercise the pre-ctor guard. Patch the ctor to
    # raise.
    def failing_async_client(**kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("synthetic ctor failure (C2 pin)")

    monkeypatch.setattr(lifespan_module.httpx, "AsyncClient", failing_async_client)

    with pytest.raises(RuntimeError, match="synthetic ctor failure"):
        async with LifespanManager(app):
            pass

    # If we get here, the ``finally`` did NOT raise UnboundLocalError —
    # the synthetic error propagated cleanly.
