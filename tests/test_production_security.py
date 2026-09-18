from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from io import BytesIO
import os
from pathlib import Path
import re
import secrets
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi import UploadFile
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.auth import hash_password, verify_password
from app.bootstrap_admin import create_admin
from app.db import Base, get_db, init_db
from app.image_uploads import (
    MAX_IMAGE_BYTES,
    ensure_image,
    save_image,
    upload_transaction,
)
from app.security import (
    MAX_REQUEST_BYTES,
    RateLimiter,
    SecurityMiddleware,
    security_settings,
)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "APP_ENV": "production",
            "SECRET_KEY": secrets.token_urlsafe(32),
            "SESSION_COOKIE_SECURE": "true",
            "PUBLIC_BASE_URL": "https://meters.example",
        }

    def test_production_rejects_missing_weak_keys_and_insecure_configuration(self):
        for changes in (
            {"SECRET_KEY": ""},
            {"SECRET_KEY": "dev-secret"},
            {"SECRET_KEY": "x" * 40},
            {"SECRET_KEY": "skift-denne-til-en-lang-tilfaeldig-vaerdi"},
            {"SESSION_COOKIE_SECURE": "false"},
            {"PUBLIC_BASE_URL": "http://meters.example"},
            {"PUBLIC_BASE_URL": "https://user:password@meters.example"},
            {"PUBLIC_BASE_URL": "https://meters.example/subpath"},
            {"APP_ENV": "prodution"},
        ):
            with (
                self.subTest(changes=changes),
                patch.dict(os.environ, self.env | changes, clear=True),
            ):
                with self.assertRaises(RuntimeError):
                    security_settings()

    def test_valid_production_and_local_development(self):
        with patch.dict(os.environ, self.env, clear=True):
            settings = security_settings()
            self.assertTrue(settings.production)
            self.assertTrue(settings.secure_cookie)
            self.assertEqual(settings.allowed_host, "meters.example")
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(security_settings().production)


class ProductionSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = "test-password-with-entropy-123"
        cls.password_hash = hash_password(cls.password)

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        self.sessions = sessionmaker(bind=self.engine)
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        with self.sessions() as db:
            users = [
                models.User(username=name, role=role, password_hash=self.password_hash)
                for name, role in [
                    ("admin", models.UserRole.ADMIN),
                    ("vvs", models.UserRole.VVS),
                    ("other", models.UserRole.VVS),
                    ("viewer", models.UserRole.USER),
                ]
            ]
            db.add_all(users)
            db.flush()
            self.user_ids = {user.username: user.id for user in users}
            address = models.Address(
                street="Testvej", house_no="1", zip="1000", city="Testby"
            )
            db.add(address)
            db.flush()
            appointment = models.Appointment(
                address_id=address.id,
                contractor_id=self.user_ids["vvs"],
                starts_at=datetime(2026, 10, 1, 8),
                ends_at=datetime(2026, 10, 1, 8, 30),
                status=models.AppointmentStatus.SCHEDULED,
            )
            db.add(appointment)
            db.flush()
            self.appointment_id = appointment.id
            self.address_id = address.id
            db.add(
                models.AppointmentPhoto(
                    appointment_id=appointment.id,
                    address_id=address.id,
                    file_path="test.jpg",
                    photo_type="old",
                )
            )
            db.add(
                models.ResidentLink(
                    address_id=address.id,
                    appointment_id=appointment.id,
                    token="resident-test-token",
                    active=True,
                )
            )
            db.commit()
        (self.root / "test.jpg").write_bytes(self.png())
        # Patch both dependency-injected sessions and startup/error-handler sessions.
        # Never open the real application database during HTTP tests.
        from app import main

        self.main = main
        self.env = {
            "APP_ENV": "production",
            "SECRET_KEY": secrets.token_urlsafe(32),
            "SESSION_COOKIE_SECURE": "true",
            "PUBLIC_BASE_URL": "https://testserver",
        }
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, self.env, clear=True).start()
        patch("app.db.engine", self.engine).start()
        patch("app.db.SessionLocal", self.sessions).start()
        patch("app.main.SessionLocal", self.sessions).start()
        for module in ("uploads", "admin_appointments", "vvs_tasks", "admin_addresses"):
            patch(f"app.routes.{module}.UPLOAD_DIR", self.root).start()
        # Build an isolated app using the actual application router and lifespan.
        from fastapi import FastAPI
        from starlette.middleware.sessions import SessionMiddleware
        from starlette.middleware.trustedhost import TrustedHostMiddleware

        self.app = FastAPI(lifespan=main.app.router.lifespan_context)
        self.app.router.routes = main.app.router.routes[:]
        self.app.exception_handlers = main.app.exception_handlers.copy()
        self.app.add_middleware(
            SecurityMiddleware,
            limiter=RateLimiter(self.root / "limits.db", self.env["SECRET_KEY"]),
            production=True,
        )
        self.app.add_middleware(
            SessionMiddleware,
            secret_key=self.env["SECRET_KEY"],
            session_cookie="vand_session",
            https_only=True,
            same_site="lax",
        )
        self.app.add_middleware(TrustedHostMiddleware, allowed_hosts=["testserver"])

        def test_db():
            with self.sessions() as db:
                yield db

        self.app.dependency_overrides[get_db] = test_db
        self.client = TestClient(
            self.app, base_url="https://testserver", follow_redirects=False
        )
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    @staticmethod
    def png():
        output = BytesIO()
        Image.new("RGB", (4, 4), "red").save(output, format="PNG")
        return output.getvalue()

    def csrf(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        return re.search(r'name="csrf-token" content="([^"]+)"', response.text)[1]

    def login(self, username="admin"):
        response = self.client.post(
            "/login",
            data={
                "username": username,
                "password": self.password,
                "csrf_token": self.csrf(),
            },
        )
        self.assertEqual(response.status_code, 303)
        return self.csrf()

    def test_secure_cookie_headers_and_host_validation(self):
        response = self.client.get("/login")
        cookie = response.headers["set-cookie"].lower()
        for flag in ("secure", "httponly", "samesite=lax"):
            self.assertIn(flag, cookie)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["referrer-policy"], "no-referrer")
        self.assertIn("max-age=", response.headers["strict-transport-security"])
        self.assertEqual(
            self.client.get("/login", headers={"host": "attacker.example"}).status_code,
            400,
        )

    def test_login_csrf_missing_wrong_valid_and_rotation(self):
        token = self.csrf()
        for value in (None, "wrong"):
            data = {"username": "admin", "password": self.password}
            if value is not None:
                data["csrf_token"] = value
            self.assertEqual(self.client.post("/login", data=data).status_code, 403)
        self.assertEqual(self.client.get("/admin/status").status_code, 303)
        self.assertEqual(
            self.client.post(
                "/login",
                data={
                    "username": "admin",
                    "password": self.password,
                    "csrf_token": token,
                },
            ).status_code,
            303,
        )
        fresh = self.csrf()
        self.assertNotEqual(token, fresh)
        self.assertEqual(
            self.client.post("/logout", data={"csrf_token": token}).status_code, 403
        )
        self.assertEqual(
            self.client.post("/logout", data={"csrf_token": fresh}).status_code, 303
        )
        self.assertEqual(self.client.get("/admin/status").status_code, 303)

    def test_json_mutation_requires_csrf_and_office_role(self):
        token = self.login()
        url = f"/admin/addresses/{self.address_id}/coordinates"
        data = {"latitude": 55.7, "longitude": 12.5}
        self.assertEqual(self.client.post(url, json=data).status_code, 403)
        self.assertEqual(
            self.client.post(
                url, json=data, headers={"X-CSRF-Token": token}
            ).status_code,
            200,
        )
        self.client.cookies.clear()
        token = self.login("vvs")
        self.assertEqual(
            self.client.post(
                url,
                json={"latitude": 0, "longitude": 0},
                headers={"X-CSRF-Token": token},
            ).status_code,
            403,
        )
        with self.sessions() as db:
            self.assertAlmostEqual(
                float(db.get(models.Address, self.address_id).latitude), 55.7
            )

    def test_private_upload_access_and_path_escape(self):
        self.assertEqual(self.client.get("/upload/test.jpg").status_code, 303)
        for username, expected in (
            ("viewer", 200),
            ("other", 404),
            ("vvs", 200),
            ("admin", 200),
        ):
            self.client.cookies.clear()
            self.login(username)
            response = self.client.get("/upload/test.jpg")
            self.assertEqual(response.status_code, expected, username)
            if expected == 200:
                self.assertEqual(response.headers["cache-control"], "no-store")
        (self.root / "untracked.jpg").write_bytes(self.png())
        self.assertEqual(self.client.get("/upload/untracked.jpg").status_code, 404)
        with TemporaryDirectory() as other_dir:
            outside = Path(other_dir) / "outside.jpg"
            outside.write_bytes(self.png())
            (self.root / "escape.jpg").symlink_to(outside)
            self.assertEqual(self.client.get("/upload/escape.jpg").status_code, 404)
        self.assertEqual(
            self.client.get("/upload/%2e%2e/requirements.txt").status_code, 404
        )

    def test_other_contractors_cannot_change_task(self):
        token = self.login("other")
        response = self.client.post(
            f"/vvs/tasks/{self.appointment_id}/complete", data={"csrf_token": token}
        )
        self.assertIn(response.status_code, (303, 404))
        with self.sessions() as db:
            self.assertEqual(
                db.get(models.Appointment, self.appointment_id).status,
                models.AppointmentStatus.SCHEDULED,
            )
        self.client.cookies.clear()
        token = self.login("vvs")
        self.assertEqual(
            self.client.post(
                f"/vvs/tasks/{self.appointment_id}/complete", data={"csrf_token": token}
            ).status_code,
            303,
        )
        with self.sessions() as db:
            self.assertEqual(
                db.get(models.Appointment, self.appointment_id).status,
                models.AppointmentStatus.COMPLETED,
            )

    def test_multipart_csrf_and_image_validation(self):
        token = self.login("vvs")
        url = f"/vvs/tasks/{self.appointment_id}/photos"
        self.assertEqual(
            self.client.post(
                url,
                data={"photo_type": "new"},
                files={"file": ("x.png", self.png(), "image/png")},
            ).status_code,
            403,
        )
        response = self.client.post(
            url,
            data={"csrf_token": token, "photo_type": "new"},
            files={"file": ("evil.html", b"<script>alert(1)</script>", "image/jpeg")},
        )
        self.assertEqual(response.status_code, 303)
        with self.sessions() as db:
            self.assertEqual(db.query(models.AppointmentPhoto).count(), 1)
        response = self.client.post(
            url,
            data={"csrf_token": token, "photo_type": "new"},
            files={"file": ("untrusted.html", self.png(), "text/html")},
        )
        self.assertEqual(response.status_code, 303)
        with self.sessions() as db:
            photo = (
                db.query(models.AppointmentPhoto)
                .filter(models.AppointmentPhoto.photo_type == "new")
                .one()
            )
            self.assertTrue(photo.file_path.endswith(".jpg"))
            self.assertEqual(
                db.get(models.Appointment, self.appointment_id).status,
                models.AppointmentStatus.COMPLETED,
            )
            saved = self.root / photo.file_path
        with Image.open(saved) as image:
            self.assertEqual(image.format, "JPEG")

    def test_request_and_image_size_limits(self):
        token = self.login("vvs")
        url = f"/vvs/tasks/{self.appointment_id}/photos"
        response = self.client.post(
            url, headers={"content-length": str(MAX_REQUEST_BYTES + 1)}
        )
        self.assertEqual(response.status_code, 413)
        response = self.client.post(
            url,
            data={"csrf_token": token, "photo_type": "new"},
            files={"file": ("big.jpg", b"x" * (MAX_IMAGE_BYTES + 1), "image/jpeg")},
        )
        self.assertEqual(response.status_code, 413)

    def test_login_rate_limit(self):
        token = self.csrf()
        for _ in range(10):
            self.assertEqual(
                self.client.post(
                    "/login",
                    data={
                        "csrf_token": token,
                        "username": "admin",
                        "password": "wrong",
                    },
                ).status_code,
                303,
            )
        response = self.client.post(
            "/login",
            data={"csrf_token": token, "username": "admin", "password": "wrong"},
        )
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response.headers["retry-after"]), 0)

    def test_resident_forms_and_invalid_links(self):
        response = self.client.get("/r/resident-test-token")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["referrer-policy"], "no-referrer")
        token = re.search(r'name="csrf_token" value="([^"]+)"', response.text)[1]
        self.assertEqual(
            self.client.post(
                "/r/resident-test-token", data={"csrf_token": "wrong"}
            ).status_code,
            403,
        )
        response = self.client.post(
            "/r/resident-test-token",
            data={
                "csrf_token": token,
                "intent": "message",
                "message": "Test",
                "request_id": "a" * 32,
            },
        )
        self.assertEqual(response.status_code, 303)
        with self.sessions() as db:
            self.assertEqual(
                db.query(models.ResidentResponse).filter_by(message="Test").count(), 1
            )
        self.assertEqual(self.client.get("/r/invalid-token").status_code, 404)

    def test_pdf_get_does_not_change_status_and_post_requires_csrf(self):
        token = self.login()
        url = f"/admin/letters/address/{self.address_id}/pdf?appointment_id={self.appointment_id}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Dan og hent PDF", response.text)
        with self.sessions() as db:
            self.assertEqual(
                db.get(models.Appointment, self.appointment_id).status,
                models.AppointmentStatus.SCHEDULED,
            )
        self.assertEqual(self.client.post(url).status_code, 403)
        response = self.client.post(url, data={"csrf_token": token})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.assertEqual(response.headers["content-type"], "application/pdf")
        with self.sessions() as db:
            self.assertEqual(
                db.get(models.Appointment, self.appointment_id).status,
                models.AppointmentStatus.INFORMED,
            )

    def test_office_user_cannot_create_users(self):
        token = self.login("viewer")
        response = self.client.post(
            "/admin/users",
            data={
                "csrf_token": token,
                "username": "intruder",
                "password": self.password,
                "role": "admin",
            },
        )
        self.assertEqual(response.status_code, 403)
        with self.sessions() as db:
            self.assertIsNone(
                db.query(models.User).filter_by(username="intruder").first()
            )

    def test_resident_rate_limit_and_inactive_link(self):
        token = self.csrf()
        url = "/r/resident-test-token"
        # Populate the shared counter without producing 60 database messages.
        limiter = RateLimiter(self.root / "limits.db", self.env["SECRET_KEY"])
        for _ in range(60):
            self.assertEqual(limiter.check([(f"resident-token:{url}", 60, 3600)]), 0)
        self.assertEqual(
            self.client.post(url, data={"csrf_token": token}).status_code, 429
        )
        with self.sessions() as db:
            db.query(models.ResidentLink).update({"active": False})
            db.commit()
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_failed_upload_rolls_back_photo_and_status(self):
        from sqlalchemy.exc import SQLAlchemyError
        from sqlalchemy.orm import Session

        token = self.login("vvs")
        before = set(self.root.rglob("*.jpg"))
        with patch.object(
            Session, "commit", side_effect=SQLAlchemyError("test failure")
        ):
            with self.assertRaises(SQLAlchemyError):
                self.client.post(
                    f"/vvs/tasks/{self.appointment_id}/photos",
                    data={"csrf_token": token, "photo_type": "new"},
                    files={"file": ("x.png", self.png(), "image/png")},
                )
        self.assertEqual(set(self.root.rglob("*.jpg")), before)
        with self.sessions() as db:
            self.assertEqual(db.query(models.AppointmentPhoto).count(), 1)
            self.assertEqual(
                db.get(models.Appointment, self.appointment_id).status,
                models.AppointmentStatus.SCHEDULED,
            )

    def test_weak_new_password_rejected_in_production(self):
        token = self.login()
        response = self.client.post(
            "/admin/users",
            data={
                "csrf_token": token,
                "username": "weak",
                "password": "short",
                "role": "vvs",
            },
        )
        self.assertEqual(response.status_code, 303)
        with self.sessions() as db:
            self.assertIsNone(db.query(models.User).filter_by(username="weak").first())

    def test_production_bootstrap_rejects_default_password(self):
        with self.sessions() as db:
            db.get(models.User, self.user_ids["admin"]).password_hash = hash_password(
                "admin123"
            )
            db.commit()
        with self.assertRaisesRegex(RuntimeError, "standard-admin"):
            init_db()
        with self.sessions() as db:
            db.query(models.User).filter(
                models.User.role == models.UserRole.ADMIN
            ).delete()
            db.commit()
        with self.assertRaisesRegex(RuntimeError, "bootstrap_admin"):
            init_db()
        with self.sessions() as db:
            self.assertIsNone(
                db.query(models.User)
                .filter(models.User.role == models.UserRole.ADMIN)
                .first()
            )
            create_admin(db, "new-admin", self.password)
            self.assertTrue(
                verify_password(
                    self.password,
                    db.query(models.User)
                    .filter_by(username="new-admin")
                    .one()
                    .password_hash,
                )
            )
            with self.assertRaises(ValueError):
                create_admin(db, "second-admin", self.password)
        init_db()


class UploadAndRateLimitTests(unittest.TestCase):
    def test_shared_atomic_rate_limits_expire_without_storing_tokens(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "limits.db"
            first = RateLimiter(path, "test-key")
            second = RateLimiter(path, "test-key")
            with ThreadPoolExecutor(max_workers=4) as executor:
                results = list(
                    executor.map(
                        lambda i: (first if i % 2 else second).check(
                            [("secret-resident-token", 5, 60)], now=100
                        ),
                        range(12),
                    )
                )
            self.assertEqual(results.count(0), 5)
            self.assertEqual(
                second.check([("secret-resident-token", 5, 60)], now=161), 0
            )
            self.assertNotIn(b"secret-resident-token", path.read_bytes())

    def test_corrupt_svg_and_oversized_images_rejected(self):
        for content in (
            b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
            b"not a picture",
            ProductionSecurityTests.png()[:24],
        ):
            self.assertFalse(
                ensure_image(UploadFile(filename="image.jpg", file=BytesIO(content)))
            )
        with patch("app.image_uploads.MAX_IMAGE_PIXELS", 1):
            self.assertFalse(
                ensure_image(
                    UploadFile(
                        filename="image.png",
                        file=BytesIO(ProductionSecurityTests.png()),
                    )
                )
            )

    def test_failed_database_commit_removes_new_file(self):
        from unittest.mock import Mock

        with TemporaryDirectory() as directory:
            root = Path(directory)
            relative = save_image(
                UploadFile(file=BytesIO(ProductionSecurityTests.png())), root, root
            )
            db = Mock()
            db.commit.side_effect = RuntimeError("commit failed")
            with self.assertRaises(RuntimeError):
                with upload_transaction(db, root / relative):
                    pass
            db.rollback.assert_called_once()
            self.assertFalse((root / relative).exists())
