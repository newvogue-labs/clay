"""Add review feedback tables."""

from alembic import op
import sqlalchemy as sa


revision = "0004_e9_review_feedback"
down_revision = "0003_e8_demo_tracking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS review")
    op.create_table(
        "signal_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("signal_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("strategy_mode", sa.String(length=32), nullable=True),
        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.Column("confidence_band", sa.String(length=32), nullable=True),
        sa.Column("outcome_status", sa.String(length=32), nullable=True),
        sa.Column("feedback_label", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        schema="review",
    )


def downgrade() -> None:
    op.drop_table("signal_feedback", schema="review")
