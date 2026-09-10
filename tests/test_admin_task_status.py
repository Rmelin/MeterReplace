from __future__ import annotations

from datetime import date, datetime, time, timedelta
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request

from app import models
from app.db import Base
from app.routes.admin_appointments import mark_blocked, mark_completed, mark_not_home


class AdminTaskStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.admin = models.User(
            username="admin",
            password_hash="test",
            role=models.UserRole.ADMIN,
        )
        self.contractor = models.User(
            username="vvs",
            password_hash="test",
            role=models.UserRole.VVS,
        )
        self.address = models.Address(
            street="Testvej",
            house_no="1",
            zip="1000",
            city="Testby",
        )
        self.db.add_all([self.admin, self.contractor, self.address])
        self.db.flush()
        starts_at = datetime.combine(date(2026, 9, 24), time(8, 0))
        self.appointment = models.Appointment(
            address_id=self.address.id,
            contractor_id=self.contractor.id,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=30),
            status=models.AppointmentStatus.SCHEDULED,
        )
        self.db.add(self.appointment)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def request(self, action: str) -> Request:
        return Request(
            {
                "type": "http",
                "method": "POST",
                "path": f"/admin/appointments/{self.appointment.id}/{action}",
                "headers": [],
                "session": {},
            }
        )

    def test_admin_can_complete_task_without_photos(self) -> None:
        request = self.request("complete")

        response = mark_completed(
            request=request,
            appointment_id=self.appointment.id,
            date_query="2026-09-24",
            db=self.db,
            user=self.admin,
        )

        self.db.refresh(self.appointment)
        self.assertEqual(self.appointment.status, models.AppointmentStatus.COMPLETED)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "/admin/appointments?date_query=2026-09-24",
        )
        self.assertIn("mangler stadig fotos", request.session["_flashes"][0]["message"])

    def test_admin_can_mark_task_as_not_home(self) -> None:
        response = mark_not_home(
            request=self.request("not-home"),
            appointment_id=self.appointment.id,
            date_query="2026-09-24",
            db=self.db,
            user=self.admin,
        )

        self.db.refresh(self.appointment)
        self.assertEqual(self.appointment.status, models.AppointmentStatus.NOT_HOME)
        self.assertEqual(response.status_code, 303)

    def test_admin_can_mark_meter_error_for_rescheduling(self) -> None:
        response = mark_blocked(
            request=self.request("blocked"),
            appointment_id=self.appointment.id,
            date_query="2026-09-24",
            db=self.db,
            user=self.admin,
        )

        self.db.refresh(self.appointment)
        self.db.refresh(self.address)
        self.assertEqual(
            self.appointment.status,
            models.AppointmentStatus.NEEDS_RESCHEDULE,
        )
        self.assertEqual(self.address.blocked_reason, "Fejl ved måler")
        self.assertEqual(response.status_code, 303)


if __name__ == "__main__":
    unittest.main()
