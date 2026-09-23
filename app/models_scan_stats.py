from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ScanDailyStat(Base):
    """Compact all-time scan statistics grouped by target, barcode and UTC day.

    Raw Activity rows remain useful for recent/history UI, but long-term counters
    no longer need one database row per physical scan forever.
    """

    __tablename__ = "scan_daily_stats"

    target_type: Mapped[str] = mapped_column(String, primary_key=True)
    target_id: Mapped[str] = mapped_column(String, primary_key=True)
    barcode: Mapped[str] = mapped_column(String, primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    target_name: Mapped[str | None] = mapped_column(String, nullable=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_scan: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_scan: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class BarcodeDailyStat(Base):
    """One durable counter per physical barcode/day, independent of target fan-out."""

    __tablename__ = "barcode_daily_stats"

    barcode: Mapped[str] = mapped_column(String, primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_scan: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_scan: Mapped[datetime] = mapped_column(DateTime, nullable=False)
