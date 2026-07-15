"""Тесты для ExecutionProofDecision ORM + ProofDecisionRepository.

Покрытие: round-trip (insert→select), JSON serde-симметрия, from_record
field-mapping, migration up/down smoke.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from clay.db.models_ops import ExecutionProofDecision
from clay.db.repositories_ops import ProofDecisionRepository
from clay.execution.proof.decision import Decision, DecisionRecord, InvariantResult
from clay.execution.proof.reason_codes import ReasonCode

pytestmark = pytest.mark.usefixtures("sqlite_session_factory")

NOW = datetime.now(tz=timezone.utc)


def _make_record(**overrides: object) -> DecisionRecord:
    defaults: dict[str, object] = dict(
        decision=Decision.ADMIT,
        intent_hash="a" * 16,
        snapshot_hash="b" * 16,
        snapshot_ts=NOW,
        metadata_version="v1",
        invariant_results=(
            InvariantResult(code=ReasonCode.UNSUPPORTED_ORDER_TYPE, passed=True),
            InvariantResult(code=ReasonCode.NOTIONAL_ABOVE_CAP, passed=False),
        ),
        reason_codes=(ReasonCode.NOTIONAL_ABOVE_CAP,),
        created_at=NOW,
        arming_event_id=None,
    )
    defaults.update(overrides)  # type: ignore[arg-type]
    return DecisionRecord(**defaults)  # type: ignore[call-overload]


class TestFromRecord:
    def test_basic_mapping(self) -> None:
        record = _make_record()
        orm = ExecutionProofDecision.from_record(
            record, symbol="BTC/USDT", client_order_id="cid-001"
        )
        assert orm.decision == "ADMIT"
        assert orm.intent_hash == "a" * 16
        assert orm.symbol == "BTC/USDT"
        assert orm.client_order_id == "cid-001"
        assert orm.event_id is not None
        assert len(orm.event_id) == 36  # uuid4

    def test_enum_serialization_by_name(self) -> None:
        record = _make_record(
            decision=Decision.DENY,
            reason_codes=(ReasonCode.NOTIONAL_UNCOMPUTABLE, ReasonCode.SNAPSHOT_STALE),
        )
        orm = ExecutionProofDecision.from_record(
            record, symbol="ETH/USDT", client_order_id="cid-002"
        )
        assert orm.decision == "DENY"
        codes = json.loads(orm.reason_codes)
        assert codes == ["NOTIONAL_UNCOMPUTABLE", "SNAPSHOT_STALE"]

    def test_invariant_results_json(self) -> None:
        record = _make_record()
        orm = ExecutionProofDecision.from_record(
            record, symbol="BTC/USDT", client_order_id="cid-003"
        )
        results = json.loads(orm.invariant_results)
        assert len(results) == 2
        assert results[0] == {"code": "UNSUPPORTED_ORDER_TYPE", "passed": True}
        assert results[1] == {"code": "NOTIONAL_ABOVE_CAP", "passed": False}

    def test_custom_event_id(self) -> None:
        record = _make_record()
        orm = ExecutionProofDecision.from_record(
            record,
            symbol="BTC/USDT",
            client_order_id="cid-004",
            event_id="custom-id",
        )
        assert orm.event_id == "custom-id"


class TestRoundTrip:
    def test_insert_and_select(self, sqlite_session_factory) -> None:
        record = _make_record()
        orm = ExecutionProofDecision.from_record(
            record, symbol="BTC/USDT", client_order_id="cid-rt-001"
        )
        with sqlite_session_factory() as session:
            repo = ProofDecisionRepository(session)
            repo.append(orm)
            session.commit()

        with sqlite_session_factory() as session:
            repo = ProofDecisionRepository(session)
            found = repo.latest_for_client_order_id("cid-rt-001")
            assert found is not None
            assert found.decision == "ADMIT"
            assert found.symbol == "BTC/USDT"

    def test_json_serde_symmetry(self, sqlite_session_factory) -> None:
        record = _make_record(
            reason_codes=(ReasonCode.QTY_BELOW_MIN, ReasonCode.EVAL_ERROR),
            invariant_results=(
                InvariantResult(code=ReasonCode.QTY_BELOW_MIN, passed=False),
                InvariantResult(code=ReasonCode.EVAL_ERROR, passed=False),
            ),
        )
        orm = ExecutionProofDecision.from_record(
            record, symbol="SOL/USDT", client_order_id="cid-serde-001"
        )
        with sqlite_session_factory() as session:
            repo = ProofDecisionRepository(session)
            repo.append(orm)
            session.commit()

        with sqlite_session_factory() as session:
            repo = ProofDecisionRepository(session)
            found = repo.latest_for_client_order_id("cid-serde-001")
            assert found is not None
            codes = json.loads(found.reason_codes)
            assert codes == ["QTY_BELOW_MIN", "EVAL_ERROR"]
            results = json.loads(found.invariant_results)
            assert len(results) == 2
            assert results[0]["code"] == "QTY_BELOW_MIN"
            assert results[0]["passed"] is False

    def test_list_by_symbol(self, sqlite_session_factory) -> None:
        with sqlite_session_factory() as session:
            repo = ProofDecisionRepository(session)
            for i in range(3):
                record = _make_record()
                orm = ExecutionProofDecision.from_record(
                    record,
                    symbol="BTC/USDT",
                    client_order_id=f"cid-list-{i}",
                    event_id=f"evt-{i}",
                )
                repo.append(orm)
            session.commit()

        with sqlite_session_factory() as session:
            repo = ProofDecisionRepository(session)
            results = repo.list_by_symbol("BTC/USDT")
            assert len(results) == 3


class TestMigrationSmoke:
    def test_upgrade_downgrade(self) -> None:
        """Реальный up/down прогон revision 0024 через alembic Operations."""
        import importlib.util
        from pathlib import Path

        from sqlalchemy import inspect as sa_inspect

        from alembic.operations import Operations
        from alembic.runtime.migration import MigrationContext

        from clay.db.session import build_engine
        from clay.settings.ingestion import IngestionSettings

        engine = build_engine(
            IngestionSettings(database_url="sqlite+pysqlite:///:memory:")
        )

        migration_path = (
            Path(__file__).resolve().parents[2]
            / "alembic/versions/0024_execution_proof_decisions.py"
        )
        spec = importlib.util.spec_from_file_location(
            "migration_0024",
            migration_path,
        )
        assert spec is not None and spec.loader is not None
        mig = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mig)

        assert mig.revision == "0024_execution_proof_decisions"
        assert mig.down_revision == "0023_knowledge_external_id"

        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                mig.upgrade()

            inspector = sa_inspect(conn)
            assert inspector.has_table("execution_proof_decisions") is True
            indexes = {
                idx["name"]
                for idx in inspector.get_indexes("execution_proof_decisions")
            }
            assert "ix_execution_proof_decisions_symbol_created_at" in indexes
            assert "ix_execution_proof_decisions_decision_created_at" in indexes

            with Operations.context(ctx):
                mig.downgrade()

            assert sa_inspect(conn).has_table("execution_proof_decisions") is False
