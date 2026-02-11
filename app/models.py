from __future__ import annotations

import enum
from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text, Time
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
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    INFORMED = "informed"
    COMPLETED = "completed"
    CLOSED = "closed"
    NOT_HOME = "not_home"
    NEEDS_RESCHEDULE = "needs_reschedule"


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    address_id: Mapped[int] = mapped_column(Integer, ForeignKey("addresses.id"), nullable=False)
    contractor_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus, native_enum=False, create_constraint=False),
        default=AppointmentStatus.DRAFT,
        nullable=False,
    )
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

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    address_id: Mapped[int] = mapped_column(Integer, ForeignKey("addresses.id"), nullable=False)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ResidentResponse(Base):
    __tablename__ = "resident_responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    address_id: Mapped[int] = mapped_column(Integer, ForeignKey("addresses.id"), nullable=False)
    appointment_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("appointments.id"), nullable=True
    )
    response_type: Mapped[str] = mapped_column(String(40), nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
