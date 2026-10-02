from __future__ import annotations

import base64
from datetime import timedelta
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from pywebpush import WebPushException
from requests import Response
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import models
from app.db import Base
from app.push_notifications import (
    enqueue_message_pushes,
    process_pending_deliveries,
    push_is_configured,
)
from app.routes.push import validate_endpoint
from app.timeutils import utc_now


class PushNotificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.admin = models.User(
            username="admin",
            password_hash="test",
            role=models.UserRole.ADMIN,
        )
        self.db.add(self.admin)
        self.db.flush()
        self.subscription = models.PushSubscription(
            user_id=self.admin.id,
            endpoint="https://web.push.apple.com/test",
            p256dh="p256dh",
            auth="auth",
        )
        self.db.add(self.subscription)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def add_message(self, status=models.ResidentMessageStatus.NEW):
        message = models.ResidentResponse(
            address_id=1,
            response_type="buffer_note",
            message="Testbesked",
            mailbox_status=status,
        )
        self.db.add(message)
        return message

    def test_new_message_is_queued_for_active_admin_subscription(self) -> None:
        message = self.add_message()

        queued = enqueue_message_pushes(self.db, message)
        self.db.commit()

        self.assertEqual(queued, 1)
        delivery = self.db.query(models.PushDelivery).one()
        self.assertEqual(delivery.resident_response_id, message.id)
        self.assertEqual(delivery.subscription_id, self.subscription.id)

    def test_non_new_message_is_not_queued(self) -> None:
        message = self.add_message(models.ResidentMessageStatus.READ)

        self.assertEqual(enqueue_message_pushes(self.db, message), 0)

    def test_worker_marks_successful_delivery_as_sent(self) -> None:
        message = self.add_message()
        enqueue_message_pushes(self.db, message)
        self.db.commit()

        result = process_pending_deliveries(self.db, sender=lambda *_: None)

        self.assertEqual(result, {"sent": 1, "retried": 0, "failed": 0})
        delivery = self.db.query(models.PushDelivery).one()
        self.assertIsNotNone(delivery.sent_at)
        self.assertEqual(self.subscription.failure_count, 0)

    def test_worker_retries_temporary_error(self) -> None:
        message = self.add_message()
        enqueue_message_pushes(self.db, message)
        self.db.commit()
        before = utc_now()

        def fail(*_):
            raise RuntimeError("temporary")

        result = process_pending_deliveries(self.db, sender=fail)

        self.assertEqual(result, {"sent": 0, "retried": 1, "failed": 0})
        delivery = self.db.query(models.PushDelivery).one()
        self.assertEqual(delivery.attempts, 1)
        self.assertGreaterEqual(delivery.next_attempt_at, before + timedelta(minutes=1))

    def test_worker_disables_expired_subscription(self) -> None:
        message = self.add_message()
        enqueue_message_pushes(self.db, message)
        self.db.commit()
        response = Response()
        response.status_code = 410

        def expired(*_):
            raise WebPushException("expired", response)

        result = process_pending_deliveries(self.db, sender=expired)

        self.assertEqual(result, {"sent": 0, "retried": 0, "failed": 1})
        self.assertIsNotNone(self.subscription.disabled_at)
        self.assertIsNotNone(self.db.query(models.PushDelivery).one().failed_at)

    def test_worker_retries_vapid_authentication_error(self) -> None:
        message = self.add_message()
        enqueue_message_pushes(self.db, message)
        self.db.commit()
        response = Response()
        response.status_code = 403

        def authentication_error(*_):
            raise WebPushException("authentication failed", response)

        result = process_pending_deliveries(self.db, sender=authentication_error)

        self.assertEqual(result, {"sent": 0, "retried": 1, "failed": 0})
        self.assertIsNone(self.subscription.disabled_at)

    def test_worker_retries_apple_idle_timeout(self) -> None:
        message = self.add_message()
        enqueue_message_pushes(self.db, message)
        self.db.commit()
        response = Response()
        response.status_code = 400
        response.headers["Content-Type"] = "application/json"
        response._content = b'{"reason":"IdleTimeout"}'

        def idle_timeout(*_):
            raise WebPushException("idle timeout", response)

        result = process_pending_deliveries(self.db, sender=idle_timeout)

        self.assertEqual(result, {"sent": 0, "retried": 1, "failed": 0})
        self.assertIsNone(self.db.query(models.PushDelivery).one().failed_at)

    def test_only_apple_push_endpoints_are_accepted(self) -> None:
        self.assertEqual(
            validate_endpoint("https://web.push.apple.com/example"),
            "https://web.push.apple.com/example",
        )
        with self.assertRaises(HTTPException):
            validate_endpoint("https://localhost/push")

    def test_vapid_configuration_requires_matching_key_pair(self) -> None:
        private_key = ec.generate_private_key(ec.SECP256R1())
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_bytes = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        public_key = base64.urlsafe_b64encode(public_bytes).rstrip(b"=").decode()

        with TemporaryDirectory() as directory:
            private_path = Path(directory) / "vapid.pem"
            private_path.write_bytes(private_pem)
            environment = {
                "VAPID_PRIVATE_KEY": str(private_path),
                "VAPID_PUBLIC_KEY": public_key,
                "VAPID_SUBJECT": "mailto:test@example.dk",
            }
            with patch.dict(os.environ, environment, clear=False):
                self.assertTrue(push_is_configured())
                os.environ["VAPID_PUBLIC_KEY"] = "wrong-key"
                self.assertFalse(push_is_configured())


if __name__ == "__main__":
    unittest.main()
