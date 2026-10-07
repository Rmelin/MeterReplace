from __future__ import annotations

from datetime import datetime, timedelta
import unittest
from types import SimpleNamespace

from fastapi.templating import Jinja2Templates

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request

from app import models
from app.db import Base
from app.routes.admin_letters import get_or_create_link
from app.routes.resident import resident_form, resident_form_context, resident_submit
from app.routes.admin_messages import message_dashboard, update_message_status


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
                "query_string": b"",
                "app": SimpleNamespace(
                    state=SimpleNamespace(
                        templates=Jinja2Templates(directory="app/templates")
                    )
                ),
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
            phone="12345678" if intent in {"message", "time"} else "",
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
        self.submit("time", "1" * 32, "new_day", "Kan ikke denne dag")
        self.submit("time", "2" * 32, "new_day", "Stadig ikke muligt")

        self.db.refresh(self.appointment)
        self.assertEqual(
            self.appointment.status,
            models.AppointmentStatus.NEEDS_RESCHEDULE,
        )
        self.assertEqual(self.db.query(models.StockMovement).count(), 1)
        self.assertEqual(self.db.query(models.AddressUnavailablePeriod).count(), 1)
        self.assertEqual(self.db.query(models.ResidentResponse).count(), 2)

    def test_same_day_preference_is_saved_with_reschedule_request(self) -> None:
        response = resident_submit(
            request=self.request(),
            token=self.link.token,
            intent="time",
            request_id="3" * 32,
            answer="same_day",
            message="Kan være hjemme fra kl. 14:00",
            phone="12345678",
            email="",
            db=self.db,
        )

        self.assertEqual(response.status_code, 303)
        saved = self.db.query(models.ResidentResponse).one()
        self.assertEqual(
            saved.message,
            "Den planlagte dag passer. Kan være hjemme fra kl. 14:00",
        )
        self.assertEqual(saved.mailbox_status, models.ResidentMessageStatus.NEW)
        self.assertEqual(self.db.query(models.AddressUnavailablePeriod).count(), 0)

    def test_contact_details_can_be_updated_independently(self) -> None:
        response = resident_submit(
            request=self.request(),
            token=self.link.token,
            intent="contact",
            request_id="4" * 32,
            name="Anna Andersen",
            phone="12345678",
            email="anna@example.dk",
            db=self.db,
        )

        self.assertEqual(response.status_code, 303)
        self.db.refresh(self.address)
        self.assertEqual(self.address.customer_name, "Anna Andersen")
        self.assertEqual(self.address.customer_phone, "12345678")
        self.assertEqual(self.address.customer_email, "anna@example.dk")

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

    def reply(self, request_id="b" * 32, **values):
        fields = dict(
            pit="",
            location="",
            time_answer="",
            preference="",
            message="",
            name="",
            phone="",
            email="",
        )
        fields.update(values)
        return resident_submit(
            request=self.request(),
            token=self.link.token,
            intent="reply",
            request_id=request_id,
            db=self.db,
            **fields,
        )

    def test_combined_reply_creates_one_entry_and_one_push_even_when_retried(self):
        admin = models.User(
            username="admin", password_hash="test", role=models.UserRole.ADMIN
        )
        self.db.add(admin)
        self.db.flush()
        self.db.add(
            models.PushSubscription(
                user_id=admin.id,
                endpoint="https://example.com/push",
                p256dh="key",
                auth="key",
            )
        )
        self.db.commit()
        fields = dict(
            pit="yes",
            location="Ved hækken",
            time_answer="same_day",
            preference="Hjemme efter 14",
            message="Ring før besøget",
            name="Anna",
            phone="12345678",
        )
        self.assertEqual(self.reply(**fields).status_code, 303)
        self.assertEqual(self.reply(**fields).status_code, 303)
        saved = self.db.query(models.ResidentResponse).one()
        self.assertEqual(saved.response_type, "combined")
        self.assertEqual(saved.meter_pit_location, "Ved hækken")
        self.assertEqual(saved.time_preference, "Hjemme efter 14")
        self.assertEqual(saved.message, "Ring før besøget")
        self.assertEqual(saved.phone, "12345678")
        self.assertEqual(self.db.query(models.PushDelivery).count(), 1)
        self.assertEqual(self.db.query(models.StockMovement).count(), 1)
        self.db.refresh(self.address)
        self.assertEqual(self.address.customer_phone, "12345678")
        self.assertEqual(self.address.buffer_note, "Ved hækken")
        self.assertEqual(
            resident_form_context(self.db, self.link)["time_response"].id, saved.id
        )

    def test_pit_and_confirmation_need_no_contact_and_preserve_existing_contact(self):
        self.address.customer_phone = "87654321"
        self.db.commit()
        self.assertEqual(
            self.reply(pit="yes", location="Ved skel", time_answer="yes").status_code,
            303,
        )
        saved = self.db.query(models.ResidentResponse).one()
        self.assertIsNone(saved.phone)
        self.db.refresh(self.address)
        self.assertEqual(self.address.customer_phone, "87654321")
        self.assertEqual(self.reply(request_id="c" * 32, pit="no").status_code, 303)
        self.db.refresh(self.address)
        self.assertIsNone(self.address.buffer_note)
        context = resident_form_context(self.db, self.link)
        self.assertEqual(context["meter_pit_response"].meter_pit_answer, "no")
        self.assertEqual(context["time_response"].answer, "yes")

    def test_missing_contact_rejects_entire_reply_and_preserves_entered_values(self):
        for extra in (
            {"message": "Hvornår kommer I?"},
            {"time_answer": "new_day"},
            {"time_answer": "same_day", "preference": "Efter 14"},
        ):
            with self.subTest(extra=extra):
                response = self.reply(pit="yes", location="Ved hækken", **extra)
                self.assertEqual(response.status_code, 400)
                self.assertIn("Angiv telefon eller e-mail", response.body.decode())
                self.assertIn("Ved hækken", response.body.decode())
                self.assertEqual(self.db.query(models.ResidentResponse).count(), 0)
                self.assertEqual(self.db.query(models.StockMovement).count(), 0)
                self.db.refresh(self.address)
                self.db.refresh(self.appointment)
                self.assertFalse(self.address.buffer_flag)
                self.assertEqual(
                    self.appointment.status, models.AppointmentStatus.SCHEDULED
                )

    def test_email_alone_is_enough_and_inbox_uses_submitted_contact(self):
        self.reply(message="Et spørgsmål", email="anna@example.dk")
        self.address.customer_email = "changed@example.dk"
        self.db.commit()
        response = message_dashboard(
            self.request(), db=self.db, user=SimpleNamespace(role=models.UserRole.ADMIN)
        )
        html = response.body.decode()
        self.assertIn("mailto:anna@example.dk", html)
        self.assertNotIn("mailto:changed@example.dk", html)

    def test_combined_reply_is_in_each_relevant_filter_and_can_be_moved(self):
        self.reply(
            pit="yes",
            location="Ved skel",
            time_answer="yes",
            message="Ring",
            phone="12345678",
        )
        user = SimpleNamespace(
            role=models.UserRole.ADMIN, id=self.appointment.contractor_id
        )
        for kind in ("all", "buffer_note", "confirm_time", "message"):
            response = message_dashboard(
                self.request(), response_type=kind, db=self.db, user=user
            )
            self.assertEqual(len(response.context["messages"]), 1)
        response = message_dashboard(
            self.request(), response_type="reschedule_request", db=self.db, user=user
        )
        self.assertEqual(len(response.context["messages"]), 0)
        saved = self.db.query(models.ResidentResponse).one()
        update_message_status(
            self.request(),
            saved.id,
            mailbox_status="TODO",
            folder="new",
            response_type="all",
            db=self.db,
            user=user,
        )
        response = message_dashboard(
            self.request(), folder="todo", db=self.db, user=user
        )
        self.assertEqual(len(response.context["messages"]), 1)

    def test_validation_checks_pit_time_lengths_email_and_terminal_appointments(self):
        invalid = [
            dict(pit="yes"),
            dict(time_answer="same_day", phone="123"),
            dict(message="Spørgsmål", email="invalid"),
            dict(pit="maybe"),
            dict(message="x" * 4001, phone="123"),
            dict(pit="yes", location="x" * 256),
        ]
        for values in invalid:
            self.assertEqual(self.reply(**values).status_code, 400)
        self.appointment.status = models.AppointmentStatus.CANCELLED
        self.db.commit()
        self.assertEqual(
            self.reply(time_answer="new_day", phone="123").status_code, 400
        )
        self.assertEqual(self.db.query(models.ResidentResponse).count(), 0)
        page = resident_form(self.request(), self.link.token, db=self.db).body.decode()
        self.assertIn("Aftalen er bortfaldet", page)
        self.assertNotIn('select name="time"', page)

    def test_new_day_replies_release_stock_and_block_day_only_once(self):
        self.reply(time_answer="new_day", phone="123")
        self.reply(request_id="c" * 32, time_answer="new_day", phone="123")
        self.assertEqual(self.db.query(models.ResidentResponse).count(), 2)
        self.assertEqual(self.db.query(models.StockMovement).count(), 1)
        self.assertEqual(self.db.query(models.AddressUnavailablePeriod).count(), 1)

    def test_legacy_message_also_requires_contact(self):
        resident_submit(
            request=self.request(),
            token=self.link.token,
            intent="message",
            request_id="c" * 32,
            message="Et spørgsmål",
            phone="",
            email="",
            db=self.db,
        )
        self.assertEqual(self.db.query(models.ResidentResponse).count(), 0)

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
