from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request

from app import models
from app.db import Base
from app.routes.admin_letters import get_or_create_link
from app.routes.resident import resident_form_context, resident_submit


class ResidentSelfServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        contractor = models.User(
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
        self.db.add_all([contractor, self.address])
        self.db.flush()
        starts_at = datetime(2026, 9, 20, 8, 0)
        self.appointment = models.Appointment(
            address_id=self.address.id,
            contractor_id=contractor.id,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=30),
            status=models.AppointmentStatus.SCHEDULED,
        )
        self.db.add(self.appointment)
        self.db.flush()
        self.link = models.ResidentLink(
            address_id=self.address.id,
            appointment_id=self.appointment.id,
            token="a" * 32,
            active=True,
        )
        self.db.add(self.link)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def request(self) -> Request:
        return Request(
            {
                "type": "http",
                "method": "POST",
                "path": f"/r/{self.link.token}",
                "headers": [],
                "session": {},
            }
        )

    def submit(
        self,
        intent: str,
        request_id: str,
        answer: str = "",
        message: str = "",
    ):
        return resident_submit(
            request=self.request(),
            token=self.link.token,
            intent=intent,
            request_id=request_id,
            answer=answer,
            message=message,
            phone="",
            email="",
            db=self.db,
        )

    def test_meter_pit_answer_is_independent_and_link_stays_active(self) -> None:
        response = self.submit("meter_pit", "1" * 32, "yes", "Ved skel")

        self.assertEqual(response.status_code, 303)
        self.db.refresh(self.address)
        self.db.refresh(self.link)
        self.assertTrue(self.address.buffer_flag)
        self.assertEqual(self.address.buffer_note, "Ved skel")
        self.assertTrue(self.link.active)
        saved = self.db.query(models.ResidentResponse).one()
        self.assertEqual(saved.answer, "yes")
        self.assertEqual(saved.resident_link_id, self.link.id)
        self.assertEqual(saved.mailbox_status, models.ResidentMessageStatus.NEW)

    def test_meter_pit_answer_can_be_updated_to_no(self) -> None:
        self.submit("meter_pit", "1" * 32, "yes", "Ved skel")
        self.submit("meter_pit", "2" * 32, "no")

        self.db.refresh(self.address)
        self.assertFalse(self.address.buffer_flag)
        self.assertIsNone(self.address.buffer_note)
        context = resident_form_context(self.db, self.link)
        self.assertEqual(context["meter_pit_response"].answer, "no")
        self.assertEqual(self.db.query(models.ResidentResponse).count(), 2)

    def test_reschedule_side_effects_only_run_once(self) -> None:
        self.submit("time", "1" * 32, "no", "Kan ikke denne dag")
        self.submit("time", "2" * 32, "no", "Stadig ikke muligt")

        self.db.refresh(self.appointment)
        self.assertEqual(
            self.appointment.status,
            models.AppointmentStatus.NEEDS_RESCHEDULE,
        )
        self.assertEqual(self.db.query(models.StockMovement).count(), 1)
        self.assertEqual(self.db.query(models.AddressUnavailablePeriod).count(), 1)
        self.assertEqual(self.db.query(models.ResidentResponse).count(), 2)

    def test_free_message_does_not_require_other_answers(self) -> None:
        self.submit("message", "1" * 32, message="Ring gerne til mig")

        saved = self.db.query(models.ResidentResponse).one()
        self.assertEqual(saved.response_type, "message")
        self.assertEqual(saved.message, "Ring gerne til mig")
        self.assertIsNone(saved.answer)
        self.assertEqual(saved.mailbox_status, models.ResidentMessageStatus.NEW)

    def test_request_id_prevents_duplicate_submission(self) -> None:
        self.submit("message", "1" * 32, message="En besked")
        self.submit("message", "1" * 32, message="En besked")

        self.assertEqual(self.db.query(models.ResidentResponse).count(), 1)

    def test_letter_link_is_reused_only_for_same_appointment(self) -> None:
        reused = get_or_create_link(self.db, self.address, self.appointment)
        self.assertEqual(reused.id, self.link.id)

        later = models.Appointment(
            address_id=self.address.id,
            contractor_id=self.appointment.contractor_id,
            starts_at=self.appointment.starts_at + timedelta(days=1),
            ends_at=self.appointment.ends_at + timedelta(days=1),
            status=models.AppointmentStatus.SCHEDULED,
        )
        self.db.add(later)
        self.db.commit()

        new_link = get_or_create_link(self.db, self.address, later)

        self.assertNotEqual(new_link.id, self.link.id)
        self.assertNotEqual(new_link.token, self.link.token)


if __name__ == "__main__":
    unittest.main()
