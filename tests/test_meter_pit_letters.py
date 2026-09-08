from __future__ import annotations

from datetime import date, datetime, timedelta
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import models
from app.db import Base
from app.routes.admin_planning import (
    committed_appointments_for_date,
    compute_plan_from_addresses,
)


class MeterPitLetterTests(unittest.TestCase):
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
            buffer_flag=True,
            buffer_note="Ved skel",
        )
        self.db.add_all([self.contractor, self.address])
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_meter_pit_plan_requires_letter(self) -> None:
        starts_at = datetime(2026, 9, 20, 8, 0)
        with (
            patch(
                "app.routes.admin_planning.build_slots",
                return_value=[
                    (self.contractor, starts_at, starts_at + timedelta(minutes=30))
                ],
            ),
            patch("app.routes.admin_planning.available_stock", return_value=1),
        ):
            planned, _, _, _ = compute_plan_from_addresses(
                self.db,
                starts_at.date(),
                [self.address],
            )

        self.assertTrue(planned[0].is_buffer)
        self.assertTrue(planned[0].letter_required)

    def test_committed_meter_pit_keeps_buffer_identity(self) -> None:
        starts_at = datetime(2026, 9, 20, 8, 0)
        self.db.add(
            models.Appointment(
                address_id=self.address.id,
                contractor_id=self.contractor.id,
                starts_at=starts_at,
                ends_at=starts_at + timedelta(minutes=30),
                status=models.AppointmentStatus.SCHEDULED,
                letter_required=True,
            )
        )
        self.db.commit()

        rows = committed_appointments_for_date(self.db, date(2026, 9, 20))

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["letter_required"])
        self.assertTrue(rows[0]["is_buffer"])


if __name__ == "__main__":
    unittest.main()
