from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Literal

from PIL import Image, ImageOps, UnidentifiedImageError


ImageKind = Literal["avatar", "banner"]
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 24_000_000


class ProfileImageError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProcessedProfileImage:
    content: bytes
    width: int
    height: int
    mime_type: str = "image/webp"


def process_profile_image(payload: bytes, kind: ImageKind) -> ProcessedProfileImage:
    if not payload:
        raise ProfileImageError("Файл зображення порожній")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise ProfileImageError("Зображення повинно важити не більше 5 МБ")

    previous_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        with Image.open(BytesIO(payload)) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"}:
                raise ProfileImageError("Підтримуються лише PNG, JPEG та WebP")
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise ProfileImageError("Зображення має занадто велику роздільну здатність")
            source.seek(0)
            image = ImageOps.exif_transpose(source).convert("RGB")
    except ProfileImageError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ProfileImageError("Потрібне справжнє PNG, JPEG або WebP-зображення") from exc
    finally:
        Image.MAX_IMAGE_PIXELS = previous_limit

    if kind == "avatar":
        image = ImageOps.fit(
            image,
            (512, 512),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
    elif kind == "banner":
        image = ImageOps.fit(
            image,
            (1600, 500),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
    else:
        raise ProfileImageError("Невідомий тип зображення")

    output = BytesIO()
    image.save(output, format="WEBP", quality=82, method=6)
    return ProcessedProfileImage(
        content=output.getvalue(),
        width=image.width,
        height=image.height,
    )
