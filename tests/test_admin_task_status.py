from __future__ import annotations

from datetime import date, datetime, time, timedelta
import unittest
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.templating import Jinja2Templates

from app import models
from app.db import Base
from app.day_agenda import day_agenda
from app.routes.admin_addresses import status_label_and_key
from app.routes.admin_appointments import (
    complete_remaining,
    keep_scheduled,
    mark_blocked,
    mark_completed,
    mark_not_home,
    appointment_overview,
)


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

    def test_actual_change_date_preserves_plan_and_appears_on_both_days(self) -> None:
        self.appointment.starts_at = datetime(2026, 10, 8, 8)
        self.appointment.ends_at = datetime(2026, 10, 8, 8, 30)
        self.db.commit()
        response = mark_completed(
            request=self.request("complete"), appointment_id=self.appointment.id,
            actual_changed_on="2026-10-01", date_query="2026-10-08",
            db=self.db, user=self.admin,
        )
        self.db.refresh(self.appointment)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.appointment.starts_at.date(), date(2026, 10, 8))
        self.assertEqual(self.appointment.actual_changed_on, date(2026, 10, 1))
        self.assertEqual(status_label_and_key(self.appointment, 2026, False), ("Skiftet 01/10", "completed"))
        for day in (date(2026, 10, 1), date(2026, 10, 8)):
            agenda = day_agenda(self.db, day)
            self.assertEqual(len(agenda), 1)
            self.assertEqual(agenda[0]["changed_on"], date(2026, 10, 1))
            self.assertEqual(agenda[0]["planned_on"], date(2026, 10, 8))
        request = self.request("overview")
        request.scope["app"] = SimpleNamespace(state=SimpleNamespace(templates=Jinja2Templates(directory="app/templates")))
        rendered = appointment_overview(request, date_query="2026-10-01", db=self.db, user=self.admin)
        html = rendered.body.decode()
        self.assertIn("Skiftet 01/10/2026", html)
        self.assertIn("Planlagt 08/10/2026", html)
        self.assertIn("Ret skiftedato", html)

    def test_invalid_actual_date_does_not_complete_visit(self) -> None:
        for raw_date in ("invalid", "2099-01-01"):
            request = self.request("complete")
            response = mark_completed(
                request=request, appointment_id=self.appointment.id,
                actual_changed_on=raw_date, date_query="2026-09-24",
                db=self.db, user=self.admin,
            )
            self.assertEqual(response.status_code, 303)
            self.assertEqual(self.appointment.status, models.AppointmentStatus.SCHEDULED)
            self.assertIsNone(self.appointment.actual_changed_on)
            self.assertEqual(request.session["_flashes"][0]["category"], "error")

    def test_correction_and_note_changes_keep_actual_date(self) -> None:
        for changed_on in ("2026-09-23", "2026-09-22"):
            mark_completed(
                request=self.request("complete"), appointment_id=self.appointment.id,
                actual_changed_on=changed_on, date_query="2026-09-24",
                db=self.db, user=self.admin,
            )
        self.appointment.notes = "Ny note"
        self.appointment.changed_date = datetime(2026, 10, 2)
        self.db.commit()
        self.assertEqual(self.appointment.meter_changed_on, date(2026, 9, 22))
        self.assertEqual(self.appointment.starts_at.date(), date(2026, 9, 24))

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

    def test_admin_can_keep_resident_reschedule_on_planned_day(self) -> None:
        self.appointment.status = models.AppointmentStatus.NEEDS_RESCHEDULE
        resident_response = models.ResidentResponse(
            address_id=self.address.id,
            appointment_id=self.appointment.id,
            response_type="reschedule_request",
            answer="same_day",
            message="Den planlagte dag passer. Kan være hjemme fra kl. 14:00",
            mailbox_status=models.ResidentMessageStatus.NEW,
        )
        self.db.add_all(
            [
                resident_response,
                models.StockMovement(
                    movement_type=models.InventoryMovementType.RELEASE,
                    quantity=1,
                    note="Beboer ønsker nyt tidspunkt",
                ),
            ]
        )
        self.db.commit()

        response = keep_scheduled(
            request=self.request("keep-scheduled"),
            appointment_id=self.appointment.id,
            date_query="2026-09-24",
            db=self.db,
            user=self.admin,
        )

        self.db.refresh(self.appointment)
        self.assertEqual(self.appointment.status, models.AppointmentStatus.SCHEDULED)
        self.assertEqual(
            self.db.query(models.StockMovement).order_by(models.StockMovement.id.desc()).first().quantity,
            -1,
        )
        self.assertEqual(response.status_code, 303)

    def test_admin_can_complete_all_remaining_tasks_for_selected_day(self) -> None:
        informed = self.add_appointment(
            house_no="2",
            starts_at=datetime(2026, 9, 24, 8, 30),
            status=models.AppointmentStatus.INFORMED,
        )
        not_home = self.add_appointment(
            house_no="3",
            starts_at=datetime(2026, 9, 24, 9, 0),
            status=models.AppointmentStatus.NOT_HOME,
        )
        future = self.add_appointment(
            house_no="4",
            starts_at=datetime(2026, 9, 25, 8, 0),
            status=models.AppointmentStatus.SCHEDULED,
        )
        manual_task = models.Appointment(
            address_id=None,
            contractor_id=self.contractor.id,
            starts_at=datetime(2026, 9, 24, 9, 30),
            ends_at=datetime(2026, 9, 24, 10, 0),
            status=models.AppointmentStatus.SCHEDULED,
            notes="Manuel opgave uden adresse",
        )
        self.db.add(manual_task)
        self.db.commit()
        request = self.request("complete-remaining")

        response = complete_remaining(
            request=request,
            date_query="2026-09-24",
            db=self.db,
            user=self.admin,
        )

        for appointment in (self.appointment, informed, not_home, future, manual_task):
            self.db.refresh(appointment)
        self.assertEqual(self.appointment.status, models.AppointmentStatus.COMPLETED)
        self.assertEqual(informed.status, models.AppointmentStatus.COMPLETED)
        self.assertEqual(not_home.status, models.AppointmentStatus.NOT_HOME)
        self.assertEqual(future.status, models.AppointmentStatus.SCHEDULED)
        self.assertEqual(manual_task.status, models.AppointmentStatus.SCHEDULED)
        self.assertEqual(response.status_code, 303)
        self.assertIn("2 resterende opgaver", request.session["_flashes"][0]["message"])

    def add_appointment(
        self,
        house_no: str,
        starts_at: datetime,
        status: models.AppointmentStatus,
    ) -> models.Appointment:
        address = models.Address(
            street="Testvej",
            house_no=house_no,
            zip="1000",
            city="Testby",
        )
        self.db.add(address)
        self.db.flush()
        appointment = models.Appointment(
            address_id=address.id,
            contractor_id=self.contractor.id,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=30),
            status=status,
        )
        self.db.add(appointment)
        self.db.commit()
        return appointment


if __name__ == "__main__":
    unittest.main()
