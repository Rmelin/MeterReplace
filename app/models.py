from __future__ import annotations

import enum
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    VVS = "vvs"
    USER = "user"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Address(Base):
    __tablename__ = "addresses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    street: Mapped[str] = mapped_column(String(200), nullable=False)
    house_no: Mapped[str] = mapped_column(String(50), nullable=False)
    zip: Mapped[str] = mapped_column(String(20), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    customer_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    buffer_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    buffer_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    blocked_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    old_meter_no: Mapped[str | None] = mapped_column(String(120), nullable=True)
    new_meter_no: Mapped[str | None] = mapped_column(String(120), nullable=True)
    register_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class AddressUnavailablePeriod(Base):
    __tablename__ = "address_unavailable_periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    address_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("addresses.id"), nullable=True
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class InventoryMovementType(str, enum.Enum):
    PURCHASE = "purchase"
    RESERVE = "reserve"
    RELEASE = "release"
    ADJUST = "adjust"


class MeterBatch(Base):
    __tablename__ = "meter_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    purchased_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    meter_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    movement_type: Mapped[InventoryMovementType] = mapped_column(
        Enum(InventoryMovementType), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    batch_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("meter_batches.id"), nullable=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)


class VvsAvailability(Base):
    __tablename__ = "vvs_availability"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class AppointmentStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    NOT_SCHEDULED = "NOTSCHEDULED"
    SCHEDULED = "SCHEDULED"
    INFORMED = "INFORMED"
    COMPLETED = "COMPLETED"
    CLOSED = "CLOSED"
    NOT_HOME = "NOT_HOME"
    NEEDS_RESCHEDULE = "NEEDS_RESCHEDULE"




class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    address_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("addresses.id"), nullable=True
    )
    contractor_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus, native_enum=False, create_constraint=False),
        default=AppointmentStatus.DRAFT,
        nullable=False,
    )
    letter_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    old_meter_no: Mapped[str | None] = mapped_column(String(120), nullable=True)
    new_meter_no: Mapped[str | None] = mapped_column(String(120), nullable=True)
    changed_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    changed_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )


    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class StreetPriority(Base):
    __tablename__ = "street_priorities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    street: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class AppSetting(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class AppointmentPhoto(Base):
    __tablename__ = "appointment_photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    appointment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("appointments.id"), nullable=False
    )
    address_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("addresses.id"), nullable=False
    )
    file_path: Mapped[str] = mapped_column(String(255), nullable=False)
    photo_type: Mapped[str] = mapped_column(String(20), nullable=False, default="both")
    uploaded_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LetterTemplate(Base):
    __tablename__ = "letter_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    body_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    logo_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    include_resident_link: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ResidentLink(Base):
    __tablename__ = "resident_links"
    __table_args__ = (
        Index("ix_resident_links_address_appointment_active", "address_id", "appointment_id", "active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    address_id: Mapped[int] = mapped_column(Integer, ForeignKey("addresses.id"), nullable=False)
    appointment_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("appointments.id"), nullable=True
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ResidentMessageStatus(str, enum.Enum):
    NEW = "NEW"
    TODO = "TODO"
    READ = "READ"
    ARCHIVED = "ARCHIVED"


class ResidentResponse(Base):
    __tablename__ = "resident_responses"
    __table_args__ = (
        Index(
            "ix_resident_responses_mailbox_status_created_at",
            "mailbox_status",
            "created_at",
        ),
        Index(
            "ix_resident_responses_link_type_created",
            "resident_link_id",
            "response_type",
            "created_at",
        ),
        Index("ux_resident_responses_request_id", "request_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    address_id: Mapped[int] = mapped_column(Integer, ForeignKey("addresses.id"), nullable=False)
    appointment_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("appointments.id"), nullable=True
    )
    resident_link_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("resident_links.id"), nullable=True
    )
    response_type: Mapped[str] = mapped_column(String(40), nullable=False)
    answer: Mapped[str | None] = mapped_column(String(20), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    mailbox_status: Mapped[ResidentMessageStatus | None] = mapped_column(
        Enum(ResidentMessageStatus, native_enum=False, create_constraint=False),
        nullable=True,
    )
    mailbox_status_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    mailbox_status_updated_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"
    __table_args__ = (
        Index("ix_push_subscriptions_user_disabled", "user_id", "disabled_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    endpoint: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    p256dh: Mapped[str] = mapped_column(String(255), nullable=False)
    auth: Mapped[str] = mapped_column(String(255), nullable=False)
    expiration_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PushDelivery(Base):
    __tablename__ = "push_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "resident_response_id",
            "subscription_id",
            name="uq_push_delivery_response_subscription",
        ),
        Index(
            "ix_push_deliveries_pending",
            "sent_at",
            "failed_at",
            "next_attempt_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resident_response_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("resident_responses.id"), nullable=False
    )
    subscription_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("push_subscriptions.id"), nullable=False
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
