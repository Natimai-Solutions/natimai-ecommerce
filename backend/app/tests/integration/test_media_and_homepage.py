"""Integration tests (real DB, local storage in a temp dir): upload an image,
serve it, put it on the homepage, and refuse to delete it while it is used."""

from __future__ import annotations

import datetime
import io
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import UploadFile
from PIL import Image
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.requests import Request

from app.api.routes.homepage import (
    create_block,
    delete_block,
    get_homepage,
    list_blocks,
    replace_block,
)
from app.api.routes.media import delete_media, list_media, serve_media, upload_media
from app.core.config import settings
from app.core.errors import AppError
from app.features.attachment.storage.factory import reset_file_storage_cache
from app.features.content.models import HomepageBlockPublic, HomepageBlockWrite
from app.features.product.models.category import Category
from app.features.user.models.user import User


@pytest.fixture(autouse=True)
def local_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setattr(settings, "FILE_STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "FILE_STORAGE_LOCAL_ROOT", str(tmp_path))
    monkeypatch.setattr(settings, "MEDIA_PUBLIC_BASE_URL", "https://api.exemple.pf")
    reset_file_storage_cache()
    yield tmp_path
    reset_file_storage_cache()


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "scheme": "http",
            "server": ("testserver", 80),
            "path": "/",
            "headers": [],
            "query_string": b"",
        }
    )


def _jpeg(size: tuple[int, int] = (2000, 1000)) -> UploadFile:
    buffer = io.BytesIO()
    Image.new("RGB", size, (30, 60, 90)).save(buffer, format="JPEG")
    buffer.seek(0)
    return UploadFile(file=buffer, filename="vitrine.jpg")


async def _fresh(db_session: AsyncSession, user: User) -> User:
    """Each route call commits, which expires the shared session's objects;
    in production every request has its own session."""
    await db_session.refresh(user)
    return user


async def _admin(db_session: AsyncSession) -> User:
    admin = User(
        email=f"admin+{uuid.uuid4().hex[:8]}@test.local",
        is_active=True,
        is_superuser=True,
        hashed_password="x",
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest.mark.asyncio
async def test_upload_serve_and_list(
    db_session: AsyncSession, local_storage: Path
) -> None:
    admin = await _admin(db_session)
    asset = await upload_media(
        _request(),
        db_session,
        await _fresh(db_session, admin),
        file=_jpeg(),
        kind="homepage",
        alt="Atelier",
    )
    assert asset.kind == "homepage" and asset.alt == "Atelier"
    assert (asset.width, asset.height) == (1600, 800)
    assert [v.width for v in asset.variants] == [480, 960, 1600]
    assert asset.url == f"https://api.exemple.pf/api/v1/media/{asset.id}/1600.webp"
    assert asset.srcset.count("w,") == 2
    # The three variants are on disk; the original upload is not kept.
    stored = sorted(p.name for p in local_storage.rglob("*.webp"))
    assert stored == ["1600.webp", "480.webp", "960.webp"]

    response = await serve_media(asset.id, "960.webp", db_session)
    assert response.media_type == "image/webp"
    assert "immutable" in response.headers["cache-control"]
    with Image.open(io.BytesIO(response.body)) as served:
        assert served.format == "WEBP" and served.width == 960

    for name in ("123.webp", "960.png", "../../etc/passwd"):
        with pytest.raises(AppError) as missing:
            await serve_media(asset.id, name, db_session)
        assert missing.value.status_code == 404

    listed = await list_media(
        _request(),
        db_session,
        await _fresh(db_session, admin),
        kind="homepage",
    )
    assert [m.id for m in listed] == [asset.id]
    assert (
        await list_media(
            _request(),
            db_session,
            await _fresh(db_session, admin),
            kind="product",
        )
        == []
    )


@pytest.mark.asyncio
async def test_homepage_shows_published_blocks_within_their_dates(
    db_session: AsyncSession,
) -> None:
    admin = await _admin(db_session)
    image = await upload_media(
        _request(),
        db_session,
        await _fresh(db_session, admin),
        file=_jpeg(),
        kind="homepage",
    )
    now = datetime.datetime.now(datetime.UTC)
    day = datetime.timedelta(days=1)

    async def block(**fields: object) -> None:
        await create_block(
            HomepageBlockWrite.model_validate(fields),
            _request(),
            db_session,
            await _fresh(db_session, admin),
        )

    await block(
        kind="hero",
        title="Rentrée",
        media_id=image.id,
        is_published=True,
        cta_label="Voir",
        cta_link="/catalogue",
        alt="Bureau équipé",
    )
    await block(kind="hero", title="Brouillon", is_published=False, position=-1)
    await block(kind="banner", title="Bientôt", is_published=True, starts_at=now + day)
    await block(kind="banner", title="Fini", is_published=True, ends_at=now - day)
    await block(
        kind="banner",
        title="Écrans",
        is_published=True,
        position=2,
        image_url="https://images.exemple.pf/ecrans.webp",
    )
    await block(kind="banner", title="Portables", is_published=True, position=1)

    homepage = await get_homepage(_request(), db_session)
    assert homepage.hero is not None and homepage.hero.title == "Rentrée"
    assert homepage.hero.image is not None
    assert homepage.hero.image.src.endswith("/1600.webp")
    assert homepage.hero.image.srcset and homepage.hero.image.alt == "Bureau équipé"
    assert [b.title for b in homepage.banners] == ["Portables", "Écrans"]
    assert homepage.banners[1].image is not None
    assert homepage.banners[1].image.src == "https://images.exemple.pf/ecrans.webp"

    # The admin sees every block, published or not.
    assert (
        len(await list_blocks(_request(), db_session, await _fresh(db_session, admin)))
        == 6
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields",
    [
        {"kind": "carousel", "title": "x"},
        {"title": "x", "cta_link": "javascript:alert(1)"},
        {"title": "x", "cta_link": "//ailleurs.example"},
        {"title": "x", "image_url": "ftp://images/x.png"},
    ],
)
async def test_invalid_blocks_are_refused(
    db_session: AsyncSession, fields: dict[str, object]
) -> None:
    admin = await _admin(db_session)
    with pytest.raises(AppError) as refused:
        await create_block(
            HomepageBlockWrite.model_validate(fields),
            _request(),
            db_session,
            await _fresh(db_session, admin),
        )
    assert refused.value.status_code == 400


@pytest.mark.asyncio
async def test_media_in_use_cannot_be_deleted(
    db_session: AsyncSession, local_storage: Path
) -> None:
    admin = await _admin(db_session)
    image = await upload_media(
        _request(),
        db_session,
        await _fresh(db_session, admin),
        file=_jpeg((800, 600)),
    )
    hero = await create_block(
        HomepageBlockWrite(kind="hero", title="Hero", media_id=image.id),
        _request(),
        db_session,
        await _fresh(db_session, admin),
    )
    category = Category(name=f"Écrans {uuid.uuid4().hex[:4]}", image_url=image.url)
    db_session.add(category)
    await db_session.commit()

    with pytest.raises(AppError) as in_use:
        await delete_media(image.id, db_session, await _fresh(db_session, admin))
    assert in_use.value.status_code == 409
    usages = in_use.value.details["usages"]
    assert "Accueil : Hero" in usages and any(u.startswith("Catégorie") for u in usages)

    await replace_block(
        hero.id,
        HomepageBlockWrite(kind="hero", title="Hero"),
        _request(),
        db_session,
        await _fresh(db_session, admin),
    )
    await delete_block(hero.id, db_session, await _fresh(db_session, admin))
    category.image_url = None
    db_session.add(category)
    await db_session.commit()

    await delete_media(image.id, db_session, await _fresh(db_session, admin))
    assert list(local_storage.rglob("*.webp")) == []
    with pytest.raises(AppError):
        await serve_media(image.id, "800.webp", db_session)


@pytest.mark.asyncio
async def test_a_second_live_hero_is_refused(db_session: AsyncSession) -> None:
    """03/10/2026: one published hero per period; a scheduled one may follow."""
    admin = await _admin(db_session)
    now = datetime.datetime.now(datetime.UTC)
    day = datetime.timedelta(days=1)

    async def block(**fields: object) -> HomepageBlockPublic:
        return await create_block(
            HomepageBlockWrite.model_validate(fields),
            _request(),
            db_session,
            await _fresh(db_session, admin),
        )

    first = await block(kind="hero", title="Rentrée", is_published=True)
    with pytest.raises(AppError) as refused:
        await block(kind="hero", title="Soldes", is_published=True)
    assert refused.value.code == "homepage.hero.conflict"
    assert refused.value.details["other_title"] == "Rentrée"
    # A draft is fine, so is a hero scheduled after the first one ends.
    draft = await block(kind="hero", title="Brouillon", is_published=False)
    await replace_block(
        first.id,
        HomepageBlockWrite(
            kind="hero", title="Rentrée", is_published=True, ends_at=now + day
        ),
        _request(),
        db_session,
        await _fresh(db_session, admin),
    )
    await block(kind="hero", title="Noël", is_published=True, starts_at=now + 2 * day)
    with pytest.raises(AppError):
        await block(
            kind="hero", title="Chevauche", is_published=True, starts_at=now + day / 2
        )
    # Publishing the draft while the first is live is refused too; the first
    # may be re-saved as it is (it does not conflict with itself).
    with pytest.raises(AppError):
        await replace_block(
            draft.id,
            HomepageBlockWrite(kind="hero", title="Brouillon", is_published=True),
            _request(),
            db_session,
            await _fresh(db_session, admin),
        )
    await replace_block(
        first.id,
        HomepageBlockWrite(
            kind="hero", title="Rentrée bis", is_published=True, ends_at=now + day
        ),
        _request(),
        db_session,
        await _fresh(db_session, admin),
    )


@pytest.mark.asyncio
async def test_alt_text_is_edited_after_upload_and_reaches_the_category(
    db_session: AsyncSession,
) -> None:
    """03/10/2026: the alt of an image is changed in the media library once it
    is stored; a category tile using that image shows the new alt."""
    from app.api.routes.media import get_media, update_media
    from app.features.media.models import MediaAssetUpdate
    from app.features.media.service import alts_for_urls, asset_id_from_url

    admin = await _admin(db_session)
    image = await upload_media(
        _request(),
        db_session,
        await _fresh(db_session, admin),
        file=_jpeg((800, 600)),
        kind="category",
        alt="Écran",
    )
    assert asset_id_from_url(image.url) == image.id
    assert asset_id_from_url("https://cdn.exemple.pf/photo.jpg") is None
    assert asset_id_from_url(None) is None

    updated = await update_media(
        image.id,
        MediaAssetUpdate(alt="Écran PC 27 pouces"),
        _request(),
        db_session,
        await _fresh(db_session, admin),
    )
    assert updated.alt == "Écran PC 27 pouces"
    assert (
        await get_media(
            image.id, _request(), db_session, await _fresh(db_session, admin)
        )
    ).alt == "Écran PC 27 pouces"

    alts = await alts_for_urls(
        db_session, [image.url, "https://cdn.exemple.pf/photo.jpg", None]
    )
    assert alts == {image.url: "Écran PC 27 pouces"}
