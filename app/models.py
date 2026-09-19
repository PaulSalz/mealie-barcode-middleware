import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils import utcnow


class Item(Base):
    __tablename__ = "items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)  # mealie | manual
    aliases: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class BarcodeCache(Base):
    __tablename__ = "barcode_cache"

    barcode: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    brand: Mapped[str | None] = mapped_column(String, nullable=True)
    quantity: Mapped[str | None] = mapped_column(String, nullable=True)
    product_type: Mapped[str | None] = mapped_column(String, nullable=True)
    found: Mapped[bool] = mapped_column(Boolean, default=False)
    # Id of the shopping-list item most recently added to Mealie for this
    # barcode via a plain note (unknown/unmapped scans). Used to reconcile
    # that line once the barcode is later linked to an item. Cleared after.
    shopping_item_id: Mapped[str | None] = mapped_column(String, nullable=True)
    lookup_attempted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class BarcodeMapping(Base):
    """Map a barcode to a structured Mealie food.

    ``quantity`` and ``unit_id`` are shopping defaults for this barcode, not
    properties of the Mealie food itself. This allows two different barcodes
    to point to the same food with different default quantities/units.
    """

    __tablename__ = "barcode_mappings"

    barcode: Mapped[str] = mapped_column(String, primary_key=True)
    item_id: Mapped[str] = mapped_column(String, ForeignKey("items.id"), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    unit_id: Mapped[str | None] = mapped_column(String, nullable=True)
    mapped_by: Mapped[str] = mapped_column(String, default="manual")  # auto | auto_confirmed | manual
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RecipeBarcodeMapping(Base):
    """Map a barcode to a Mealie recipe using Mealie's native shopping-list recipe link."""

    __tablename__ = "recipe_barcode_mappings"

    barcode: Mapped[str] = mapped_column(String, primary_key=True)
    recipe_id: Mapped[str] = mapped_column(String, nullable=False)
    recipe_name: Mapped[str | None] = mapped_column(String, nullable=True)
    recipe_scale: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    mapped_by: Mapped[str] = mapped_column(String, default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    token_hash: Mapped[str] = mapped_column(String, nullable=False)
    token_prefix: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RetryQueue(Base):
    __tablename__ = "retry_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    barcode: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    barcode: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(String, nullable=False)
    result: Mapped[str] = mapped_column(String, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    is_dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SettingsOverride(Base):
    __tablename__ = "settings_overrides"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SystemState(Base):
    __tablename__ = "system_state"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str | None] = mapped_column(String, nullable=True)
