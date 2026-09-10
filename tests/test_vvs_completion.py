from __future__ import annotations

from datetime import date, datetime, time, timedelta
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request

from app import models
from app.db import Base
from app.routes.admin_missing_photos import missing_photo_rows
from app.routes.vvs_tasks import mark_completed


class VvsCompletionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
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
        self.db.add_all([self.contractor, self.address])
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

    def request(self) -> Request:
        return Request(
            {
                "type": "http",
                "method": "POST",
                "path": f"/vvs/tasks/{self.appointment.id}/complete",
                "headers": [],
                "session": {},
            }
        )

    def add_photo(self, photo_type: str) -> None:
        self.db.add(
            models.AppointmentPhoto(
                appointment_id=self.appointment.id,
                address_id=self.address.id,
                file_path=f"{photo_type}.jpg",
                photo_type=photo_type,
                uploaded_by_user_id=self.contractor.id,
            )
        )
        self.db.commit()

    def test_vvs_can_complete_task_without_photos(self) -> None:
        request = self.request()

        response = mark_completed(
            request=request,
            appointment_id=self.appointment.id,
            date_query="2026-09-24",
            db=self.db,
            user=self.contractor,
        )

        self.db.refresh(self.appointment)
        self.assertEqual(self.appointment.status, models.AppointmentStatus.COMPLETED)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/vvs/tasks?date_query=2026-09-24")
        self.assertIn("mangler stadig fotos", request.session["_flashes"][0]["message"])

    def test_admin_missing_photos_includes_incomplete_photo_set(self) -> None:
        self.appointment.status = models.AppointmentStatus.COMPLETED
        self.add_photo("new")

        rows = missing_photo_rows(self.db)

        self.assertEqual([row["appointment"].id for row in rows], [self.appointment.id])

        self.add_photo("old")

        self.assertEqual(missing_photo_rows(self.db), [])


if __name__ == "__main__":
    unittest.main()
