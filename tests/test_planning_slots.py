from __future__ import annotations

from datetime import date, datetime, time, timedelta
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request

from app import models
from app.db import Base
from app.planning_slots import availability_slots, build_slots
from app.routes.admin_planning import manual_planning_commit


class PlanningSlotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.plan_date = date(2026, 9, 20)
        self.contractor = models.User(
            username="vvs",
            password_hash="test",
            role=models.UserRole.VVS,
        )
        self.admin = models.User(
            username="admin",
            password_hash="test",
            role=models.UserRole.ADMIN,
        )
        self.address = models.Address(
            street="Testvej",
            house_no="1",
            zip="1000",
            city="Testby",
        )
        self.db.add_all([self.contractor, self.admin, self.address])
        self.db.flush()
        self.availability = models.VvsAvailability(
            user_id=self.contractor.id,
            date=self.plan_date,
            start_time=time(8, 0),
            end_time=time(16, 30),
        )
        self.db.add(self.availability)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_extended_workday_adds_complete_half_hour_slot(self) -> None:
        slots = availability_slots(self.db, self.plan_date)

        self.assertEqual(len(slots), 17)
        self.assertEqual(slots[-1][1].time(), time(16, 0))
        self.assertEqual(slots[-1][2].time(), time(16, 30))

    def test_partial_half_hour_does_not_add_slot(self) -> None:
        self.availability.end_time = time(16, 15)
        self.db.commit()

        slots = availability_slots(self.db, self.plan_date)

        self.assertEqual(len(slots), 16)
        self.assertEqual(slots[-1][2].time(), time(16, 0))

    def test_appointment_occupies_extended_slot(self) -> None:
        starts_at = datetime.combine(self.plan_date, time(16, 0))
        self.db.add(
            models.Appointment(
                address_id=self.address.id,
                contractor_id=self.contractor.id,
                starts_at=starts_at,
                ends_at=starts_at + timedelta(minutes=30),
                status=models.AppointmentStatus.SCHEDULED,
            )
        )
        self.db.commit()

        slots = build_slots(self.db, self.plan_date)

        self.assertEqual(len(slots), 16)
        self.assertEqual(slots[-1][2].time(), time(16, 0))

    def test_planning_stops_at_allowed_end_of_day(self) -> None:
        self.availability.end_time = time(18, 0)
        self.db.commit()

        slots = availability_slots(self.db, self.plan_date)

        self.assertEqual(len(slots), 20)
        self.assertEqual(slots[-1][1].time(), time(17, 30))
        self.assertEqual(slots[-1][2].time(), time(18, 0))

    def test_manual_planning_accepts_extended_slot(self) -> None:
        self.db.add(
            models.StockMovement(
                movement_type=models.InventoryMovementType.PURCHASE,
                quantity=1,
                created_by_user_id=self.admin.id,
            )
        )
        self.db.commit()
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/admin/planning/manual",
                "headers": [],
                "session": {},
            }
        )

        response = manual_planning_commit(
            request=request,
            date_raw=self.plan_date.isoformat(),
            address_id=self.address.id,
            contractor_id=self.contractor.id,
            start_raw="16:00",
            notes="",
            db=self.db,
            user=self.admin,
        )

        self.assertEqual(response.status_code, 303)
        appointment = self.db.query(models.Appointment).one()
        self.assertEqual(appointment.starts_at.time(), time(16, 0))
        self.assertEqual(appointment.ends_at.time(), time(16, 30))


if __name__ == "__main__":
    unittest.main()
