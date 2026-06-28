import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from clay.db.models_context import NewsItem, SentimentSnapshot

logger = logging.getLogger("clay.context")


class ContextRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def store_news_items(self, items: list[dict[str, object]]) -> int:
        written = 0
        for item in items:
            # SELECT-skip fast path: existing row short-circuits before INSERT.
            if self._news_exists(item):
                continue
            # Defense-in-depth via DB UniqueConstraint: catch TOCTOU race.
            # Savepoint isolates the failure so the outer session keeps
            # working for subsequent inserts in the same run_once cycle.
            try:
                with self.session.begin_nested():
                    self.session.add(NewsItem(**item))
                    self.session.flush()
            except IntegrityError:
                logger.info(
                    "clay.context: skipped duplicate news "
                    "(source=%s, headline=%s, published_at=%s)",
                    item["source_name"],
                    item["headline"],
                    item["published_at"],
                )
                continue
            written += 1

        return written

    def _news_exists(self, item: dict[str, object]) -> bool:
        return (
            self.session.scalar(
                select(NewsItem).where(
                    NewsItem.source_name == item["source_name"],
                    NewsItem.headline == item["headline"],
                    NewsItem.published_at == item["published_at"],
                ),
            )
            is not None
        )

    def store_sentiment_snapshots(self, items: list[dict[str, object]]) -> int:
        written = 0
        for item in items:
            if self._sentiment_exists(item):
                continue
            try:
                with self.session.begin_nested():
                    self.session.add(SentimentSnapshot(**item))
                    self.session.flush()
            except IntegrityError:
                logger.info(
                    "clay.context: skipped duplicate sentiment "
                    "(source=%s, symbol=%s, captured_at=%s)",
                    item["source_name"],
                    item["symbol"],
                    item["captured_at"],
                )
                continue
            written += 1

        return written

    def _sentiment_exists(self, item: dict[str, object]) -> bool:
        return (
            self.session.scalar(
                select(SentimentSnapshot).where(
                    SentimentSnapshot.source_name == item["source_name"],
                    SentimentSnapshot.symbol == item["symbol"],
                    SentimentSnapshot.captured_at == item["captured_at"],
                ),
            )
            is not None
        )

    def latest_news(self, *, limit: int = 5) -> list[NewsItem]:
        query = select(NewsItem).order_by(NewsItem.published_at.desc()).limit(limit)
        return list(self.session.scalars(query).all())

    def latest_sentiment(self, *, limit: int = 5) -> list[SentimentSnapshot]:
        query = (
            select(SentimentSnapshot)
            .order_by(
                SentimentSnapshot.captured_at.desc(),
            )
            .limit(limit)
        )
        return list(self.session.scalars(query).all())
