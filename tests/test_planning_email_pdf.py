from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from app import models
from app.routes.admin_planning import manual_schedule_map


class PlanningEmailPdfTests(unittest.TestCase):
    def test_manual_schedule_exposes_email_and_appointment_specific_ids(self) -> None:
        address = models.Address(
            id=12,
            street="Testvej",
            house_no="1",
            zip="1000",
            city="Testby",
            customer_email="beboer@example.dk",
        )
        starts_at = datetime(2026, 9, 20, 8, 0)
        appointment = models.Appointment(
            id=34,
            address_id=address.id,
            contractor_id=56,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=30),
            status=models.AppointmentStatus.SCHEDULED,
        )

        result = manual_schedule_map([(appointment, address)])

        entry = result[56][0]
        self.assertEqual(entry["customer_email"], "beboer@example.dk")
        self.assertEqual(entry["address_id"], 12)
        self.assertEqual(entry["appointment_id"], 34)
        self.assertTrue(entry["can_create_letter"])

    def test_completed_appointment_does_not_offer_pdf(self) -> None:
        address = models.Address(
            id=12,
            street="Testvej",
            house_no="1",
            zip="1000",
            city="Testby",
            customer_email="beboer@example.dk",
        )
        starts_at = datetime(2026, 9, 20, 8, 0)
        appointment = models.Appointment(
            id=34,
            address_id=address.id,
            contractor_id=56,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=30),
            status=models.AppointmentStatus.COMPLETED,
        )

        entry = manual_schedule_map([(appointment, address)])[56][0]

        self.assertFalse(entry["can_create_letter"])


if __name__ == "__main__":
    unittest.main()
