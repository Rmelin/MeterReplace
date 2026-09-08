from __future__ import annotations

import json
import mimetypes
from pathlib import Path
import unittest

from PIL import Image

from app.main import apple_touch_icon, apple_touch_icon_precomposed


STATIC_DIR = Path("app/static")


class PwaAssetTests(unittest.TestCase):
    def test_manifest_icons_exist_with_declared_dimensions(self) -> None:
        manifest_path = STATIC_DIR / "site.webmanifest"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(
            mimetypes.guess_type(manifest_path.name)[0],
            "application/manifest+json",
        )
        self.assertEqual(manifest["display"], "standalone")
        purposes = set()
        for icon in manifest["icons"]:
            icon_path = Path(icon["src"].removeprefix("/static/"))
            width, height = (int(value) for value in icon["sizes"].split("x"))
            with Image.open(STATIC_DIR / icon_path) as image:
                self.assertEqual(image.size, (width, height))
                self.assertNotIn("A", image.getbands())
            purposes.add(icon.get("purpose"))

        self.assertIn("any", purposes)
        self.assertIn("maskable", purposes)

    def test_apple_touch_icon_is_opaque_180_png(self) -> None:
        with Image.open(STATIC_DIR / "icon-180.png") as image:
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.size, (180, 180))
            self.assertNotIn("A", image.getbands())

    def test_apple_fallback_routes_return_png_directly(self) -> None:
        for response in (apple_touch_icon(), apple_touch_icon_precomposed()):
            self.assertEqual(response.media_type, "image/png")
            self.assertEqual(Path(response.path), STATIC_DIR / "icon-180.png")

    def test_base_template_declares_mobile_icons(self) -> None:
        base_template = Path("app/templates/base.html").read_text(encoding="utf-8")

        self.assertIn('rel="manifest"', base_template)
        self.assertIn('rel="apple-touch-icon" sizes="180x180"', base_template)
        self.assertIn('name="theme-color" content="#0f172a"', base_template)


if __name__ == "__main__":
    unittest.main()
