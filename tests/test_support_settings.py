from __future__ import annotations

import unittest

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.app_settings import (
    SUPPORT_EMAIL_KEY,
    SUPPORT_PHONE_HOURS_KEY,
    SUPPORT_PHONE_KEY,
    set_setting_value,
    support_contact,
)
from app.db import Base
from app.routes.admin_settings import validate_support_settings


class SupportSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_missing_contact_settings_are_empty(self) -> None:
        contact = support_contact(self.db)

        self.assertEqual(contact.email, "")
        self.assertEqual(contact.phone, "")
        self.assertEqual(contact.phone_hours, "")
        self.assertEqual(contact.phone_href, "")

    def test_contact_settings_are_loaded_and_phone_is_normalized(self) -> None:
        set_setting_value(self.db, SUPPORT_EMAIL_KEY, "drift@example.dk")
        set_setting_value(self.db, SUPPORT_PHONE_KEY, "+45 70 20 00 00")
        set_setting_value(self.db, SUPPORT_PHONE_HOURS_KEY, "Hverdage 08:00-15:00")
        self.db.commit()

        contact = support_contact(self.db)

        self.assertEqual(contact.email, "drift@example.dk")
        self.assertEqual(contact.phone, "+45 70 20 00 00")
        self.assertEqual(contact.phone_href, "+4570200000")
        self.assertEqual(contact.phone_hours, "Hverdage 08:00-15:00")

    def test_support_validation_rejects_unsafe_values(self) -> None:
        self.assertIsNotNone(validate_support_settings("ikke-en-mail", "", ""))
        self.assertIsNotNone(validate_support_settings("", "javascript:alert(1)", ""))
        self.assertIsNotNone(validate_support_settings("", "12345", "Åben\n<script>"))
        self.assertIsNone(
            validate_support_settings(
                "drift@example.dk",
                "+45 70 20 00 00",
                "Hverdage 08:00-15:00",
            )
        )

    def test_resident_error_renders_safe_contact_links(self) -> None:
        set_setting_value(self.db, SUPPORT_EMAIL_KEY, "drift@example.dk")
        set_setting_value(self.db, SUPPORT_PHONE_KEY, "+45 70 20 00 00")
        set_setting_value(self.db, SUPPORT_PHONE_HOURS_KEY, "Hverdage < 15")
        self.db.commit()
        template = Environment(
            loader=FileSystemLoader("app/templates"),
            autoescape=select_autoescape(["html"]),
        ).get_template("error.html")

        rendered = template.render(
            status_code=404,
            message="Beboerlinket kunne ikke findes.",
            is_resident_404=True,
            support_contact=support_contact(self.db),
            current_user=None,
            flashes=[],
        )

        self.assertIn('href="mailto:drift@example.dk"', rendered)
        self.assertIn('href="tel:+4570200000"', rendered)
        self.assertIn("Hverdage &lt; 15", rendered)
        self.assertNotIn("Til forsiden", rendered)


if __name__ == "__main__":
    unittest.main()
