import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils import utcnow


class Item(Base):
    __tablename__ = "items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)  # mealie | manual
    aliases: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    label_id: Mapped[str | None] = mapped_column(String, nullable=True)
    label_name: Mapped[str | None] = mapped_column(String, nullable=True)
    # default | mealie | homeassistant | both | none
    shopping_route: Mapped[str] = mapped_column(String, nullable=False, default="default")
    shopping_list_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class BarcodeCache(Base):
    __tablename__ = "barcode_cache"

    barcode: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    brand: Mapped[str | None] = mapped_column(String, nullable=True)
    custom_title: Mapped[str | None] = mapped_column(String, nullable=True)
    custom_brand: Mapped[str | None] = mapped_column(String, nullable=True)
    quantity: Mapped[str | None] = mapped_column(String, nullable=True)
    product_type: Mapped[str | None] = mapped_column(String, nullable=True)
    found: Mapped[bool] = mapped_column(Boolean, default=False)
    shopping_item_id: Mapped[str | None] = mapped_column(String, nullable=True)
    lookup_attempted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    @property
    def display_title(self) -> str | None:
        return self.custom_title or self.title

    @property
    def display_brand(self) -> str | None:
        return self.custom_brand or self.brand


class BarcodeMapping(Base):
    __tablename__ = "barcode_mappings"

    barcode: Mapped[str] = mapped_column(String, primary_key=True)
    target_type: Mapped[str] = mapped_column(String, nullable=False, default="food")  # food | recipe
    target_id: Mapped[str] = mapped_column(String, nullable=False)
    target_name: Mapped[str | None] = mapped_column(String, nullable=True)

    quantity: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    unit_id: Mapped[str | None] = mapped_column(String, nullable=True)
    recipe_scale: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    # Mainly used for recipe mappings. Food mappings normally inherit the Item route/list.
    shopping_list_id: Mapped[str | None] = mapped_column(String, nullable=True)

    mapped_by: Mapped[str] = mapped_column(String, default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    token_hash: Mapped[str] = mapped_column(String, nullable=False)
    token_prefix: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    # Optional telemetry reported by the USB scanner bridge. Phone/app tokens leave these NULL.
    scanner_version: Mapped[str | None] = mapped_column(String, nullable=True)
    scanner_hostname: Mapped[str | None] = mapped_column(String, nullable=True)
    scanner_device: Mapped[str | None] = mapped_column(String, nullable=True)
    scanner_layout: Mapped[str | None] = mapped_column(String, nullable=True)
    scanner_last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    scanner_uptime_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scanner_total_scans: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scanner_errors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scanner_last_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class RetryQueue(Base):
    __tablename__ = "retry_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    barcode: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
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
    is_scan_event: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String, nullable=True)
    target_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    target_name: Mapped[str | None] = mapped_column(String, nullable=True)
    quantity_snapshot: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit_id_snapshot: Mapped[str | None] = mapped_column(String, nullable=True)
    recipe_scale_snapshot: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Action(Base):
    __tablename__ = "actions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    aliases_json: Mapped[str] = mapped_column(Text, default="[]")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    action_type: Mapped[str] = mapped_column(String, default="webhook")
    webhook_url: Mapped[str] = mapped_column(String, nullable=False)
    method: Mapped[str] = mapped_column(String, default="POST")
    headers_json: Mapped[str] = mapped_column(Text, default="{}")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    parameters_json: Mapped[str] = mapped_column(Text, default="{}")
    connect_timeout: Mapped[float] = mapped_column(Float, default=2.0)
    read_timeout: Mapped[float] = mapped_column(Float, default=5.0)
    write_timeout: Mapped[float] = mapped_column(Float, default=5.0)
    pool_timeout: Mapped[float] = mapped_column(Float, default=2.0)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    retry_delay: Mapped[float] = mapped_column(Float, default=0.5)
    backoff_factor: Mapped[float] = mapped_column(Float, default=2.0)
    retry_policy: Mapped[str] = mapped_column(String, default="network")
    cooldown_seconds: Mapped[float] = mapped_column(Float, default=2.0)
    execution_mode: Mapped[str] = mapped_column(String, default="async")
    respect_pause: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ActionExecution(Base):
    __tablename__ = "action_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    barcode: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


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
