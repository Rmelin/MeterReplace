import io
import runpy
import unittest
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from alembic.migration import MigrationContext
from alembic.operations import Operations
from PIL import Image
from sqlalchemy import create_engine, func, inspect
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.templating import Jinja2Templates

from app import models
from app.db import Base
from app.meter_completion import complete_meter
from app.routes.admin_addresses import (
    complete_address,
    edit_address_form,
    upload_address_photo,
)
from app.routes.admin_appointments import mark_completed
from app.routes.vvs_tasks import complete_task_address


class UnplannedCompletionTests(unittest.TestCase):
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
            street="Testvej",
            house_no="1",
            zip="1000",
            city="Testby",
            blocked_reason="Defekt stophane",
        )
        self.db.add_all([self.admin, self.vvs, self.address])
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
                "method": "POST",
                "path": "/",
                "headers": [],
                "session": {},
                "app": SimpleNamespace(
                    state=SimpleNamespace(
                        templates=Jinja2Templates(directory="app/templates")
                    )
                ),
            }
        )

    def stock(self):
        return self.db.query(func.sum(models.StockMovement.quantity)).scalar()

    def complete(self, **kwargs):
        return complete_address(
            request=self.request(),
            address_id=self.address.id,
            contractor_id=self.vvs.id,
            actual_changed_on=kwargs.pop("actual_changed_on", "2026-10-01"),
            old_meter_no="old",
            new_meter_no="new",
            db=self.db,
            user=self.admin,
            **kwargs,
        )

    def appointment(self, status, stock_reserved=None):
        visit = models.Appointment(
            address_id=self.address.id,
            contractor_id=self.vvs.id,
            starts_at=datetime(2026, 10, 3, 8),
            ends_at=datetime(2026, 10, 3, 8, 30),
            status=status,
            stock_reserved=stock_reserved,
        )
        self.db.add(visit)
        self.db.commit()
        return visit

    def test_unplanned_address_deducts_once_and_clears_issue(self):
        self.assertEqual(self.complete().status_code, 303)
        visit = self.db.query(models.Appointment).one()
        self.assertEqual(visit.status, models.AppointmentStatus.COMPLETED)
        self.assertEqual(visit.actual_changed_on, date(2026, 10, 1))
        self.assertTrue(visit.stock_reserved)
        self.assertIsNone(self.address.blocked_reason)
        self.assertEqual(self.address.new_meter_no, "new")
        self.assertEqual(self.stock(), 4)
        self.complete()
        self.assertEqual(self.stock(), 4)
        self.assertEqual(self.db.query(models.Appointment).count(), 1)

    def test_not_scheduled_visit_reused(self):
        visit = self.appointment(models.AppointmentStatus.NOT_SCHEDULED)
        self.complete()
        self.assertEqual(self.db.query(models.Appointment).one().id, visit.id)
        self.assertEqual(self.stock(), 4)

    def test_reserved_issue_preserves_plan_without_second_deduction(self):
        visit = self.appointment(models.AppointmentStatus.NEEDS_RESCHEDULE, True)
        self.complete()
        self.assertEqual(visit.starts_at, datetime(2026, 10, 3, 8))
        self.assertEqual(self.stock(), 5)

    def test_released_issue_consumes_a_meter(self):
        visit = self.appointment(models.AppointmentStatus.NEEDS_RESCHEDULE, False)
        mark_completed(
            request=self.request(),
            appointment_id=visit.id,
            date_query="",
            actual_changed_on="2026-10-01",
            db=self.db,
            user=self.admin,
        )
        self.assertEqual(self.stock(), 4)
        self.assertIsNone(self.address.blocked_reason)

    def test_legacy_issue_keeps_existing_reservation(self):
        visit = self.appointment(models.AppointmentStatus.NEEDS_RESCHEDULE)
        visit.changed_by_user_id = self.vvs.id
        self.db.commit()
        self.complete()
        self.assertEqual(self.stock(), 5)

    def test_legacy_resident_rescheduling_deducts_again(self):
        self.appointment(models.AppointmentStatus.NEEDS_RESCHEDULE)
        self.complete()
        self.assertEqual(self.stock(), 4)

    def test_legacy_resident_request_still_deducts_after_admin_note(self):
        visit = self.appointment(models.AppointmentStatus.NEEDS_RESCHEDULE)
        visit.changed_by_user_id = self.admin.id
        self.db.add(
            models.ResidentResponse(
                address_id=self.address.id,
                appointment_id=visit.id,
                response_type="reschedule_request",
                answer="same_day",
            )
        )
        self.db.commit()
        self.complete()
        self.assertEqual(self.stock(), 4)

    def test_empty_stock_leaves_no_visit_and_keeps_issue(self):
        self.db.query(models.StockMovement).delete()
        self.db.commit()
        response = self.complete()
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.db.query(models.Appointment).count(), 0)
        self.assertEqual(self.address.blocked_reason, "Defekt stophane")

    def test_invalid_future_date_leaves_stock_unchanged(self):
        for raw in ["invalid", "2099-01-01"]:
            self.complete(actual_changed_on=raw)
            self.assertEqual(self.stock(), 5)
            self.assertEqual(self.db.query(models.Appointment).count(), 0)

    def test_vvs_repair_records_meter_without_changing_repair_status(self):
        task = models.Appointment(
            task_address_id=self.address.id,
            contractor_id=self.vvs.id,
            starts_at=datetime(2026, 10, 3, 8),
            ends_at=datetime(2026, 10, 3, 9),
            status=models.AppointmentStatus.SCHEDULED,
            is_manual_task=True,
        )
        self.db.add(task)
        self.db.commit()
        for _ in range(2):
            complete_task_address(
                request=self.request(),
                appointment_id=task.id,
                db=self.db,
                user=self.vvs,
            )
        self.assertEqual(self.stock(), 4)
        self.assertEqual(task.status, models.AppointmentStatus.SCHEDULED)
        self.assertEqual(self.db.query(models.Appointment).count(), 2)

    def test_another_vvs_cannot_complete_repair(self):
        from fastapi import HTTPException

        other = models.User(
            username="other", password_hash="test", role=models.UserRole.VVS
        )
        self.db.add(other)
        visit = self.appointment(models.AppointmentStatus.SCHEDULED)
        with self.assertRaises(HTTPException) as raised:
            complete_task_address(
                request=self.request(), appointment_id=visit.id, db=self.db, user=other
            )
        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(self.stock(), 5)

    def test_closed_address_cannot_consume_another_meter(self):
        self.address.register_closed = True
        self.db.commit()
        self.complete()
        self.assertEqual(self.stock(), 5)
        self.assertEqual(self.db.query(models.Appointment).count(), 0)

    def test_address_form_available_without_a_visit(self):
        response = edit_address_form(
            request=self.request(),
            address_id=self.address.id,
            edit_photos=None,
            db=self.db,
            user=self.admin,
        )
        self.assertIn("Registrér målerskift", response.body.decode())
        self.assertIn(
            f"/admin/addresses/{self.address.id}/complete", response.body.decode()
        )

    def test_photos_after_direct_completion_do_not_deduct_again(self):
        self.complete()
        image = io.BytesIO()
        Image.new("RGB", (10, 10)).save(image, format="PNG")
        image.seek(0)
        with (
            TemporaryDirectory() as folder,
            patch("app.routes.admin_addresses.UPLOAD_DIR", Path(folder)),
        ):
            response = upload_address_photo(
                request=self.request(),
                address_id=self.address.id,
                photo_type="both",
                file=UploadFile(image, filename="meter.png"),
                contractor_id=self.vvs.id,
                date_raw="2026-10-01",
                start_raw="08:00",
                duration_minutes=30,
                replacement_datetime="",
                old_meter_no="old",
                new_meter_no="new",
                force=False,
                db=self.db,
                user=self.admin,
            )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.stock(), 4)
        self.assertEqual(self.db.query(models.AppointmentPhoto).count(), 1)

    def test_stale_request_cannot_deduct_twice(self):
        visit = self.appointment(models.AppointmentStatus.NOT_SCHEDULED, False)
        with Session(self.engine) as second:
            stale_visit = second.get(models.Appointment, visit.id)
            complete_meter(self.db, visit, self.admin.id, date(2026, 10, 1))
            self.db.commit()
            complete_meter(second, stale_visit, self.admin.id, date(2026, 10, 1))
            second.commit()
        self.assertEqual(self.stock(), 4)

    def test_migration_preserves_legacy_rows(self):
        visit_id = self.appointment(models.AppointmentStatus.SCHEDULED).id
        self.db.close()
        with self.engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                migration = runpy.run_path(
                    str(
                        Path(__file__).resolve().parents[1]
                        / "alembic/versions/0031_appointment_stock_reserved.py"
                    )
                )
                migration["downgrade"]()
                migration["upgrade"]()
            self.assertIn(
                "stock_reserved",
                [c["name"] for c in inspect(connection).get_columns("appointments")],
            )
        self.assertIsNone(self.db.get(models.Appointment, visit_id).stock_reserved)
