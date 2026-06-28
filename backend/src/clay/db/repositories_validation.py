import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from clay.db.models_validation import ActivationReview, ValidationRun


class ValidationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_validation_run(self, payload: dict[str, object]) -> ValidationRun:
        row = ValidationRun(**payload)
        self.session.add(row)
        self.session.flush()
        return row

    def list_validation_runs(self, *, limit: int = 20) -> list[ValidationRun]:
        query = (
            select(ValidationRun).order_by(ValidationRun.created_at.desc()).limit(limit)
        )
        return list(self.session.scalars(query).all())

    def create_activation_review(self, payload: dict[str, object]) -> ActivationReview:
        row = ActivationReview(
            **{
                **payload,
                "evidence_json": json.dumps(
                    payload["evidence_json"], sort_keys=True, default=str
                ),
            }
        )
        self.session.add(row)
        self.session.flush()
        return row

    def get_activation_review(self, review_id: str) -> ActivationReview | None:
        query = select(ActivationReview).where(ActivationReview.review_id == review_id)
        return self.session.scalar(query)

    def list_activation_reviews(self, *, limit: int = 10) -> list[ActivationReview]:
        query = (
            select(ActivationReview)
            .order_by(ActivationReview.created_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(query).all())
