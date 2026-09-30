"""Image re-encoding for public media: formats, sizes, metadata, orientation."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.core.errors import AppError
from app.features.media.service import encode_variants, validate_kind


def _image_bytes(
    size: tuple[int, int],
    fmt: str,
    *,
    mode: str = "RGB",
    exif: Image.Exif | None = None,
) -> bytes:
    image = Image.new(
        mode, size, (200, 80, 20, 128) if mode == "RGBA" else (200, 80, 20)
    )
    buffer = io.BytesIO()
    kwargs = {"exif": exif} if exif is not None else {}
    image.save(buffer, format=fmt, **kwargs)
    return buffer.getvalue()


def test_large_jpeg_gives_three_webp_widths() -> None:
    variants = encode_variants(_image_bytes((2400, 1200), "JPEG"))
    assert [v.width for v in variants] == [480, 960, 1600]
    assert [v.height for v in variants] == [240, 480, 800]
    for variant in variants:
        with Image.open(io.BytesIO(variant.data)) as decoded:
            assert decoded.format == "WEBP"
            assert decoded.size == (variant.width, variant.height)


def test_small_image_is_never_upscaled() -> None:
    variants = encode_variants(_image_bytes((300, 200), "PNG"))
    assert [(v.width, v.height) for v in variants] == [(300, 200)]


def test_metadata_is_dropped_and_orientation_applied() -> None:
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: rotate 90° clockwise to display
    exif[0x010F] = "CameraMaker"  # Make — must not survive the re-encoding
    variants = encode_variants(_image_bytes((1000, 500), "JPEG", exif=exif))
    largest = variants[-1]
    # Portrait once the EXIF orientation is applied.
    assert (largest.width, largest.height) == (500, 1000)
    with Image.open(io.BytesIO(largest.data)) as decoded:
        assert not decoded.getexif()
        assert "exif" not in decoded.info


def test_transparency_is_kept() -> None:
    variants = encode_variants(_image_bytes((600, 600), "PNG", mode="RGBA"))
    with Image.open(io.BytesIO(variants[-1].data)) as decoded:
        assert decoded.mode == "RGBA"


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (b"not an image at all", "media.invalid"),
        (_image_bytes((50, 50), "GIF", mode="P"), "media.format"),
        (_image_bytes((50, 50), "BMP"), "media.format"),
    ],
)
def test_refused_inputs(payload: bytes, code: str) -> None:
    with pytest.raises(AppError) as refused:
        encode_variants(payload)
    assert refused.value.code == code
    assert refused.value.status_code == 400


def test_pixel_bomb_is_refused_before_decoding(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.features.media.service.MAX_PIXELS", 10_000)
    with pytest.raises(AppError) as refused:
        encode_variants(_image_bytes((200, 200), "PNG"))
    assert refused.value.code == "media.too_many_pixels"


def test_unknown_kind_is_refused() -> None:
    assert validate_kind("homepage") == "homepage"
    with pytest.raises(AppError):
        validate_kind("homepgae")
