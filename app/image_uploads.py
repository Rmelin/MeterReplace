"""Validate and re-encode raster uploads; never retain client-supplied extensions."""

from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import warnings

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


def image_bytes(file: UploadFile) -> bytes:
    file.file.seek(0)
    content = file.file.read(MAX_IMAGE_BYTES + 1)
    file.file.seek(0)
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Billedet må højst fylde 10 MiB")
    return content


def open_image(content: bytes):
    image = Image.open(BytesIO(content))
    if (
        image.format not in ALLOWED_FORMATS
        or image.width * image.height > MAX_IMAGE_PIXELS
    ):
        image.close()
        raise ValueError("Unsupported image")
    return image


def ensure_image(file: UploadFile) -> bool:
    content = image_bytes(file)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with open_image(content) as image:
                image.verify()
            with open_image(content) as image:
                image.load()
        return True
    except (
        ValueError,
        OSError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        return False


def save_image(file: UploadFile, folder: Path, root: Path) -> str:
    # Validate again so callers cannot bypass the shared upload boundary.
    if not ensure_image(file):
        raise HTTPException(400, "Vælg et gyldigt JPEG-, PNG- eller WebP-billede")
    with open_image(image_bytes(file)) as source:
        transparent = source.mode in {"RGBA", "LA"} or "transparency" in source.info
        image = ImageOps.exif_transpose(source).convert(
            "RGBA" if transparent else "RGB"
        )
        # Re-encoding strips metadata, embedded payloads and client-controlled names.
        image.info.clear()
        folder.mkdir(parents=True, exist_ok=True)
        extension = ".png" if transparent else ".jpg"
        path = folder / f"{uuid4().hex}{extension}"
        created = False
        try:
            with path.open("xb") as target:
                created = True
                image.save(target, format="PNG" if transparent else "JPEG", quality=90)
        except Exception:
            if created:
                path.unlink(missing_ok=True)
            raise
        finally:
            image.close()
    return str(path.relative_to(root))


@contextmanager
def upload_transaction(db, path: Path):
    """Remove the new file when its database transaction cannot be committed."""
    try:
        yield
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
