import runpy
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace

from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.templating import Jinja2Templates

from app import models
from app.day_agenda import day_agenda
from app.db import Base
from app.meter_completion import complete_meter
from app.planning_slots import build_slots
from app.routes.admin_addresses import complete_address, edit_address_form
from app.routes.admin_appointments import (
    appointment_overview,
    complete_remaining,
    mark_not_home,
)
from app.routes.admin_planning import fetch_addresses
from app.routes.admin_status import latest_status_map
from app.routes.resident import resident_form
from app.routes.vvs_tasks import (
    availability_dates,
    task_rows_for_date,
    vvs_tasks_map_data,
)
from app.workday_status import build_workday_status


class CompletedMeterPlanTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.admin = models.User(
            username="admin", password_hash="test", role=models.UserRole.ADMIN
        )
        self.vvs = models.User(
            username="vvs", password_hash="test", role=models.UserRole.VVS
        )
        self.address = models.Address(
            street="Testvej", house_no="1", zip="1000", city="Testby"
        )
        self.changed_on = date(2026, 9, 15)
        self.planned_on = date(2026, 11, 19)
        self.db.add_all([self.admin, self.vvs, self.address])
        self.db.flush()
        self.db.add(
            models.VvsAvailability(
                user_id=self.vvs.id,
                date=self.planned_on,
                start_time=time(8),
                end_time=time(16),
            )
        )
        self.db.add(
            models.StockMovement(
                movement_type=models.InventoryMovementType.PURCHASE, quantity=5
            )
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def request(self):
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [],
                "query_string": b"",
                "session": {},
                "app": SimpleNamespace(
                    state=SimpleNamespace(
                        templates=Jinja2Templates(directory="app/templates")
                    )
                ),
            }
        )

    def visit(
        self,
        day=None,
        status=models.AppointmentStatus.SCHEDULED,
        reserved=True,
        manual=False,
    ):
        start = datetime.combine(day or self.planned_on, time(8))
        appointment = models.Appointment(
            address_id=None if manual else self.address.id,
            task_address_id=self.address.id if manual else None,
            contractor_id=self.vvs.id,
            starts_at=start,
            ends_at=start + timedelta(minutes=30),
            status=status,
            stock_reserved=reserved,
            is_manual_task=manual,
        )
        self.db.add(appointment)
        self.db.commit()
        return appointment

    def stock(self):
        return self.db.query(func.sum(models.StockMovement.quantity)).scalar()

    def complete(self, visit):
        complete_meter(self.db, visit, self.admin.id, self.changed_on)
        self.db.commit()

    def test_same_visit_only_appears_and_counts_on_actual_date(self):
        visit = self.visit()
        self.complete(visit)
        self.assertEqual(visit.starts_at.date(), self.planned_on)
        self.assertEqual(day_agenda(self.db, self.planned_on), [])
        self.assertEqual(len(day_agenda(self.db, self.changed_on)), 1)
        self.assertEqual(task_rows_for_date(self.db, self.vvs.id, self.planned_on), [])
        self.assertEqual(
            [
                row[0].id
                for row in task_rows_for_date(self.db, self.vvs.id, self.changed_on)
            ],
            [visit.id],
        )
        self.assertIn(self.changed_on, availability_dates(self.db, self.vvs.id))
        days = {row["date"]: row for row in build_workday_status(self.db)["day_status"]}
        self.assertEqual(days[self.planned_on]["total"], 0)
        self.assertEqual(days[self.planned_on]["completed"], 0)
        self.assertEqual(days[self.changed_on]["completed"], 1)
        self.assertEqual(days[self.planned_on]["free_slots"], 16)
        planned_html = appointment_overview(
            self.request(), self.planned_on.isoformat(), self.db, self.admin
        ).body.decode()
        self.assertNotIn(f'id="appointment-{visit.id}"', planned_html)
        changed_html = appointment_overview(
            self.request(), self.changed_on.isoformat(), self.db, self.admin
        ).body.decode()
        self.assertIn(f'id="appointment-{visit.id}"', changed_html)

    def test_separate_future_plan_cancelled_and_only_unused_reservation_released(self):
        completed = self.visit(self.changed_on)
        future = self.visit()
        manual = self.visit(manual=True)
        before = self.stock()
        self.complete(completed)
        self.assertEqual(future.status, models.AppointmentStatus.CANCELLED)
        self.assertEqual(future.superseded_by_appointment_id, completed.id)
        self.assertFalse(future.stock_reserved)
        self.assertFalse(future.letter_required)
        self.assertEqual(future.starts_at.date(), self.planned_on)
        self.assertEqual(manual.status, models.AppointmentStatus.SCHEDULED)
        self.assertEqual(self.stock(), before + 1)
        self.assertEqual(
            latest_status_map(self.db, [self.address.id])[self.address.id],
            models.AppointmentStatus.COMPLETED,
        )
        self.assertEqual(
            [
                row[0].id
                for row in task_rows_for_date(self.db, self.vvs.id, self.planned_on)
            ],
            [manual.id],
        )
        self.complete(completed)
        self.assertEqual(self.stock(), before + 1)
        html = edit_address_form(
            self.request(), self.address.id, None, self.db, self.admin
        ).body.decode()
        self.assertIn("Bortfaldet – måler allerede skiftet", html)
        self.assertIn("Oprindeligt planlagt 19/11/2026", html)
        self.assertIn("Skiftet 15/09/2026", html)

    def test_cancelled_plan_frees_slot_and_completed_address_cannot_be_planned_again(
        self,
    ):
        completed = self.visit(self.changed_on)
        future = self.visit()
        self.assertEqual(len(build_slots(self.db, self.planned_on)), 15)
        self.complete(completed)
        self.assertEqual(len(build_slots(self.db, self.planned_on)), 16)
        self.assertEqual(fetch_addresses(self.db, self.planned_on)[0], [])
        with self.assertRaises(HTTPException) as raised:
            mark_not_home(
                request=self.request(),
                appointment_id=future.id,
                date_query="",
                db=self.db,
                user=self.admin,
            )
        self.assertEqual(raised.exception.status_code, 409)

    def test_released_reschedule_does_not_return_a_second_meter(self):
        completed = self.visit(self.changed_on)
        future = self.visit(
            status=models.AppointmentStatus.NEEDS_RESCHEDULE, reserved=False
        )
        before = self.stock()
        self.complete(completed)
        self.assertEqual(future.status, models.AppointmentStatus.CANCELLED)
        self.assertEqual(self.stock(), before)

    def test_empty_free_stock_can_reuse_future_reservation_for_same_address(self):
        visit = self.visit(
            self.changed_on,
            status=models.AppointmentStatus.NEEDS_RESCHEDULE,
            reserved=False,
        )
        future = self.visit()
        self.db.add(
            models.StockMovement(
                movement_type=models.InventoryMovementType.ADJUST, quantity=-5
            )
        )
        self.db.commit()
        self.complete(visit)
        self.assertEqual(visit.status, models.AppointmentStatus.COMPLETED)
        self.assertTrue(visit.stock_reserved)
        self.assertEqual(future.status, models.AppointmentStatus.CANCELLED)
        self.assertEqual(self.stock(), 0)
        self.assertEqual(
            self.db.query(models.StockMovement)
            .filter_by(movement_type=models.InventoryMovementType.RELEASE)
            .count(),
            0,
        )

    def test_resident_link_explains_cancelled_visit_without_planned_time(self):
        completed = self.visit(self.changed_on)
        future = self.visit()
        self.db.add(
            models.ResidentLink(
                address_id=self.address.id,
                appointment_id=future.id,
                token="test",
                active=True,
            )
        )
        self.db.commit()
        self.complete(completed)
        html = resident_form(self.request(), "test", self.db).body.decode()
        self.assertIn("Aftalen er bortfaldet", html)
        self.assertNotIn("Planlagt tid:", html)
        self.assertNotIn('name="intent" value="time"', html)

    def test_closed_visit_still_uses_actual_date(self):
        visit = self.visit()
        self.complete(visit)
        visit.status = models.AppointmentStatus.CLOSED
        self.db.commit()
        self.assertEqual(day_agenda(self.db, self.planned_on), [])
        self.assertEqual(len(day_agenda(self.db, self.changed_on)), 1)
        days = {row["date"]: row for row in build_workday_status(self.db)["day_status"]}
        self.assertEqual(days[self.changed_on]["closed"], 1)
        self.assertEqual(days[self.planned_on]["closed"], 0)
        self.assertEqual(len(build_slots(self.db, self.planned_on)), 16)

    def test_legacy_completion_without_actual_date_and_manual_work_remain_on_original_day(
        self,
    ):
        self.visit(status=models.AppointmentStatus.COMPLETED)
        manual = self.visit(status=models.AppointmentStatus.CLOSED, manual=True)
        manual.actual_changed_on = self.changed_on
        self.db.commit()
        self.assertEqual(len(day_agenda(self.db, self.planned_on)), 2)
        self.assertEqual(day_agenda(self.db, self.changed_on), [])

    def test_vvs_map_only_shows_replacement_on_actual_day(self):
        self.complete(self.visit())
        future = vvs_tasks_map_data(
            q=None,
            status=None,
            buffer=None,
            date=self.planned_on.isoformat(),
            db=self.db,
            user=self.vvs,
        )
        actual = vvs_tasks_map_data(
            q=None,
            status=None,
            buffer=None,
            date=self.changed_on.isoformat(),
            db=self.db,
            user=self.vvs,
        )
        self.assertEqual(future.body, b'{"addresses":[]}')
        self.assertIn(b"Testvej", actual.body)

    def test_bulk_completion_handles_two_same_day_plans_without_double_completion(self):
        first = self.visit(self.changed_on)
        second = self.visit(self.changed_on)
        response = complete_remaining(
            self.request(), self.changed_on.isoformat(), self.db, self.admin
        )
        self.assertEqual(response.status_code, 303)
        statuses = {first.status, second.status}
        self.assertEqual(
            statuses,
            {models.AppointmentStatus.COMPLETED, models.AppointmentStatus.CANCELLED},
        )

    def test_repeated_address_completion_reuses_finished_visit(self):
        completed = self.visit(
            self.changed_on, status=models.AppointmentStatus.COMPLETED
        )
        completed.actual_changed_on = self.changed_on
        future = self.visit()
        self.db.commit()
        complete_address(
            self.request(),
            self.address.id,
            self.vvs.id,
            self.changed_on.isoformat(),
            "",
            "",
            self.db,
            self.admin,
        )
        self.assertEqual(future.status, models.AppointmentStatus.CANCELLED)
        self.assertEqual(
            self.db.query(models.Appointment)
            .filter_by(status=models.AppointmentStatus.COMPLETED)
            .count(),
            1,
        )

    def test_migration_repairs_existing_separate_plans_without_touching_manual_tasks(
        self,
    ):
        completed = self.visit(
            self.changed_on, status=models.AppointmentStatus.COMPLETED
        )
        completed.actual_changed_on = self.changed_on
        future = self.visit(reserved=None)
        unreserved = self.visit(
            status=models.AppointmentStatus.NEEDS_RESCHEDULE, reserved=False
        )
        manual = self.visit(manual=True)
        self.db.commit()
        completed_id, future_id, unreserved_id, manual_id = (
            completed.id,
            future.id,
            unreserved.id,
            manual.id,
        )
        before = self.stock()
        self.db.close()
        migration = runpy.run_path(
            str(
                Path(__file__).resolve().parents[1]
                / "alembic/versions/0032_retire_superseded_meter_plans.py"
            )
        )
        with self.engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                migration["downgrade"]()
                migration["upgrade"]()
        self.assertEqual(
            self.db.get(models.Appointment, future_id).status,
            models.AppointmentStatus.CANCELLED,
        )
        self.assertEqual(
            self.db.get(models.Appointment, future_id).superseded_by_appointment_id,
            completed_id,
        )
        self.assertEqual(
            self.db.get(models.Appointment, unreserved_id).status,
            models.AppointmentStatus.CANCELLED,
        )
        self.assertEqual(
            self.db.get(models.Appointment, manual_id).status,
            models.AppointmentStatus.SCHEDULED,
        )
        self.assertEqual(self.stock(), before + 1)
