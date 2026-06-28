"""Tests for IngestionSettings defaults and env-override for MP3 fields.

MP3: 10 new fields (limit, timeout, limits×2, 5 freshness).
Each field must have a default equal to the current hardcoded value
and must be overridable via ``CLAY_`` env var (consulting the
``env_prefix`` convention). No behavioural changes — only source of
value (literal → ``settings.<field>``).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from clay.settings.ingestion import IngestionSettings
from clay.settings.scheduler import SchedulerSettings


class TestIngestionSettingsDefaults:
    def test_market_fetch_limit_default(self) -> None:
        assert IngestionSettings().market_fetch_limit == 200

    def test_market_fetch_timeout_default(self) -> None:
        assert IngestionSettings().market_fetch_timeout == 10.0

    def test_market_limits_max_connections_default(self) -> None:
        assert IngestionSettings().market_limits_max_connections == 20

    def test_market_limits_max_keepalive_default(self) -> None:
        assert IngestionSettings().market_limits_max_keepalive == 10

    def test_market_freshness_5m_default(self) -> None:
        assert IngestionSettings().market_freshness_5m_minutes == 10

    def test_market_freshness_15m_default(self) -> None:
        assert IngestionSettings().market_freshness_15m_minutes == 25

    def test_market_freshness_1h_default(self) -> None:
        assert IngestionSettings().market_freshness_1h_minutes == 80

    def test_context_freshness_news_default(self) -> None:
        assert IngestionSettings().context_freshness_news_hours == 8

    def test_context_freshness_sentiment_default(self) -> None:
        assert IngestionSettings().context_freshness_sentiment_hours == 4


class TestIngestionSettingsOverride:
    def test_override_market_fetch_limit(self, monkeypatch) -> None:
        monkeypatch.setenv("CLAY_MARKET_FETCH_LIMIT", "500")
        assert IngestionSettings().market_fetch_limit == 500

    def test_override_market_fetch_timeout(self, monkeypatch) -> None:
        monkeypatch.setenv("CLAY_MARKET_FETCH_TIMEOUT", "30.0")
        assert IngestionSettings().market_fetch_timeout == 30.0

    def test_override_market_limits_max_connections(self, monkeypatch) -> None:
        monkeypatch.setenv("CLAY_MARKET_LIMITS_MAX_CONNECTIONS", "50")
        assert IngestionSettings().market_limits_max_connections == 50

    def test_override_market_limits_max_keepalive(self, monkeypatch) -> None:
        monkeypatch.setenv("CLAY_MARKET_LIMITS_MAX_KEEPALIVE", "25")
        assert IngestionSettings().market_limits_max_keepalive == 25

    def test_override_market_freshness_5m(self, monkeypatch) -> None:
        monkeypatch.setenv("CLAY_MARKET_FRESHNESS_5M_MINUTES", "15")
        assert IngestionSettings().market_freshness_5m_minutes == 15

    def test_override_context_freshness_news(self, monkeypatch) -> None:
        monkeypatch.setenv("CLAY_CONTEXT_FRESHNESS_NEWS_HOURS", "12")
        assert IngestionSettings().context_freshness_news_hours == 12


class TestFreshnessThresholdsMethods:
    def test_market_thresholds_defaults(self) -> None:
        t = IngestionSettings().market_freshness_thresholds()
        assert t == {
            "5m": timedelta(minutes=10),
            "15m": timedelta(minutes=25),
            "1h": timedelta(minutes=80),
        }

    def test_context_thresholds_defaults(self) -> None:
        t = IngestionSettings().context_freshness_thresholds()
        assert t == {
            "news": timedelta(hours=8),
            "sentiment": timedelta(hours=4),
        }

    def test_market_thresholds_reflect_env_override(self, monkeypatch) -> None:
        monkeypatch.setenv("CLAY_MARKET_FRESHNESS_5M_MINUTES", "1")
        monkeypatch.setenv("CLAY_MARKET_FRESHNESS_15M_MINUTES", "2")
        monkeypatch.setenv("CLAY_MARKET_FRESHNESS_1H_MINUTES", "3")
        t = IngestionSettings().market_freshness_thresholds()
        assert t == {
            "5m": timedelta(minutes=1),
            "15m": timedelta(minutes=2),
            "1h": timedelta(minutes=3),
        }

    def test_context_thresholds_reflect_env_override(self, monkeypatch) -> None:
        monkeypatch.setenv("CLAY_CONTEXT_FRESHNESS_NEWS_HOURS", "1")
        monkeypatch.setenv("CLAY_CONTEXT_FRESHNESS_SENTIMENT_HOURS", "2")
        t = IngestionSettings().context_freshness_thresholds()
        assert t == {
            "news": timedelta(hours=1),
            "sentiment": timedelta(hours=2),
        }


class TestFootgunAFix:
    """FOOTGUN A: database_url is required — no silent default to live 5432."""

    def test_unset_env_raises_readable_error(self, monkeypatch) -> None:
        monkeypatch.delenv("CLAY_DATABASE_URL", raising=False)
        with pytest.raises(ValidationError) as exc:
            IngestionSettings()
        msg = str(exc.value)
        assert "database_url" in msg
        assert "Field required" in msg or "required" in msg.lower()


class TestSettingsExports:
    def test_scheduler_settings_exported(self) -> None:
        from clay.settings import SchedulerSettings as ExportedSchedulerSettings

        assert ExportedSchedulerSettings is SchedulerSettings
