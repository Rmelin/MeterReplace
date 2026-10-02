from datetime import date, datetime, time
import unittest
from pathlib import Path
import runpy

from sqlalchemy import create_engine, Integer, inspect
from sqlalchemy.orm import Session
from starlette.requests import Request
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app import models
from app.db import Base
from app.planning_slots import build_slots
from app.routes.admin_appointments import create_manual_task
from app.routes.vvs_tasks import build_day_checklist


class ManualVvsTaskTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.day = date(2026, 10, 8)
        self.admin = models.User(username="admin", password_hash="test", role=models.UserRole.ADMIN)
        self.vvs = models.User(username="vvs", password_hash="test", role=models.UserRole.VVS)
        self.address = models.Address(street="Birkevænget", house_no="5", zip="1000", city="Testby")
        self.db.add_all([self.admin, self.vvs, self.address])
        self.db.flush()
        self.db.add(models.VvsAvailability(user_id=self.vvs.id, date=self.day, start_time=time(8), end_time=time(16)))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def create(self, window, start="", duration=30, address_id=None):
        request = Request({"type": "http", "method": "POST", "path": "/admin/appointments/manual-task", "headers": [], "session": {}})
        response = create_manual_task(
            request=request, date_raw=self.day.isoformat(), contractor_id=self.vvs.id,
            start_raw=start, duration_minutes=duration, time_window=window,
            address_id=self.address.id if address_id is None else address_id,
            notes="Kontroller vandtryk", db=self.db, user=self.admin,
        )
        return response, request

    def test_afternoon_task_has_address_without_becoming_meter_visit(self):
        response, _ = self.create("afternoon")
        task = self.db.query(models.Appointment).one()
        self.assertEqual(response.status_code, 303)
        self.assertTrue(task.is_manual_task)
        self.assertIsNone(task.address_id)
        self.assertEqual(task.task_address_id, self.address.id)
        self.assertEqual((task.starts_at.time(), task.ends_at.time()), (time(12), time(16)))
        self.assertFalse(task.letter_required)
        self.assertEqual(len(build_slots(self.db, self.day)), 16)
        summary, _ = build_day_checklist([task], {task.id: self.address}, {}, {task.id: "Eftermiddag"})
        self.assertEqual(summary["missing_photos"], 0)

    def test_exact_task_blocks_its_time(self):
        response, _ = self.create("exact", "09:15", 15)
        task = self.db.query(models.Appointment).one()
        self.assertEqual(response.status_code, 303)
        self.assertEqual(task.starts_at, datetime(2026, 10, 8, 9, 15))
        self.assertEqual(task.ends_at, datetime(2026, 10, 8, 9, 30))
        self.assertEqual(len(build_slots(self.db, self.day)), 15)

    def test_invalid_address_is_rejected(self):
        response, request = self.create("morning", address_id=9999)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.db.query(models.Appointment).count(), 0)
        self.assertEqual(request.session["_flashes"][0]["category"], "error")

    def test_upgrade_repairs_legacy_required_address_and_allows_task_creation(self):
        admin_id, vvs_id, address_id = self.admin.id, self.vvs.id, self.address.id
        self.db.close()
        with self.engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                with Operations(MigrationContext.configure(connection)).batch_alter_table("appointments") as batch:
                    batch.alter_column("address_id", existing_type=Integer(), nullable=False)
                migration = runpy.run_path(str(Path(__file__).resolve().parents[1] / "alembic/versions/0029_repair_optional_appointment_address.py"))
                migration["upgrade"]()
            address_column = next(column for column in inspect(connection).get_columns("appointments") if column["name"] == "address_id")
            self.assertTrue(address_column["nullable"])
        self.admin = self.db.get(models.User, admin_id)
        self.vvs = self.db.get(models.User, vvs_id)
        self.address = self.db.get(models.Address, address_id)
        response, _ = self.create("afternoon")
        self.assertEqual(response.status_code, 303)
        task = self.db.query(models.Appointment).one()
        self.assertIsNone(task.address_id)
        self.assertEqual(task.task_address_id, self.address.id)


if __name__ == "__main__":
    unittest.main()
