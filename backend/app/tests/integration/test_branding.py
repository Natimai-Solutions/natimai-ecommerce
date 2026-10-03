"""R9 / T9 — site icon and logo chosen in the back-office (real DB)."""

from __future__ import annotations

import io
import json
from typing import Any

import pytest
from PIL import Image
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.branding import icon, logo, webmanifest
from app.api.routes.media import upload_media
from app.api.routes.system_settings import get_shop_config
from app.core import runtime_settings
from app.core.errors import AppError
from app.features.media.branding import logo_url_from_settings
from app.features.system.settings_service import write_setting
from app.tests.integration.test_media_and_homepage import (
    _admin,
    _fresh,
    _jpeg,
    _request,
)


@pytest.mark.asyncio
async def test_logo_and_icon_reach_the_storefront_config(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = await _admin(db_session)
    admin_id = admin.id  # commits below expire the instance
    logo_asset = await upload_media(
        _request(),
        db_session,
        await _fresh(db_session, admin),
        file=_jpeg((800, 200)),
        kind="branding",
    )
    icon_asset = await upload_media(
        _request(),
        db_session,
        await _fresh(db_session, admin),
        file=_jpeg((1024, 768)),
        kind="branding",
    )

    # Nothing chosen: defaults, no URLs.
    config = await get_shop_config(_request(), db_session)
    assert config.branding.logo is None and config.branding.icon is None
    assert logo_url_from_settings() is None

    await write_setting(
        db_session, "shop_logo_media_id", str(logo_asset.id), actor_id=admin_id
    )
    await write_setting(
        db_session, "shop_icon_media_id", str(icon_asset.id), actor_id=admin_id
    )
    config = await get_shop_config(_request(), db_session)
    assert config.branding.logo is not None
    assert config.branding.logo.src.endswith(f"/branding/{logo_asset.id}/logo.webp")
    assert config.branding.icon is not None
    assert config.branding.icon.sizes == [16, 32, 180, 192, 512]
    assert config.branding.icon.manifest.endswith("/site.webmanifest")
    # The e-mail and PDF renderers get the same stable URL, synchronously, from
    # the process snapshot a previous read filled (the test fixture disables
    # that snapshot: give it a TTL again for this read).
    monkeypatch.setattr(runtime_settings, "CACHE_TTL_SECONDS", 60.0)
    await runtime_settings.get("shop_logo_media_id", db_session, fresh=True)
    sync_url = logo_url_from_settings("http://testserver")
    assert sync_url is not None and sync_url.endswith(
        f"/branding/{logo_asset.id}/logo.webp"
    )

    # Derived icon sizes: square PNGs cut from the (landscape) picture.
    png = await icon(icon_asset.id, 180, db_session)
    assert png.media_type == "image/png"
    with Image.open(io.BytesIO(png.body)) as rendered:
        assert rendered.size == (180, 180)
    with pytest.raises(AppError):
        await icon(icon_asset.id, 99, db_session)

    manifest = await webmanifest(icon_asset.id, _request(), db_session)
    payload: dict[str, Any] = json.loads(bytes(manifest.body))
    assert [i["sizes"] for i in payload["icons"]] == ["192x192", "512x512"]
    assert payload["icons"][1]["src"].endswith(
        f"/branding/{icon_asset.id}/icon-512.png"
    )

    served = await logo(logo_asset.id, db_session)
    assert served.media_type == "image/webp" and len(served.body) > 0

    # Back to the defaults.
    await write_setting(db_session, "shop_logo_media_id", "", actor_id=admin_id)
    config = await get_shop_config(_request(), db_session)
    assert config.branding.logo is None
