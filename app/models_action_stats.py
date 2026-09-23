from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ActionAggregate(Base):
    """All-time action counters independent of raw execution retention."""

    __tablename__ = "action_aggregates"

    action_id: Mapped[str] = mapped_column(String, primary_key=True)
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ignored: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_sum_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_status: Mapped[str | None] = mapped_column(String, nullable=True)
    last_execution: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
