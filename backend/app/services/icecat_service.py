"""
Service for Icecat API integration.
Handles product specifications, images, and technical details retrieval.
Documentation: https://iceclog.com/manual-for-icecat-json-product-requests/
"""

# mypy: disable-error-code="arg-type,no-any-return,no-untyped-call,no-untyped-def,type-arg"

import logging
from typing import Any

import aiohttp

from app.core.config import secret_is_set, settings
from app.core.http_retry import (
    RETRYABLE_STATUSES,
    AsyncRateLimiter,
    RetryableHTTPError,
    parse_retry_after,
    request_with_retry,
)
from app.features.integrations.models.icecat_sync import IcecatProductData

logger = logging.getLogger(__name__)

# Explicit HTTP timeout: aiohttp's default (300 s total) would let a slow
# Icecat response pin an ARQ enrichment job until its 600 s job_timeout.
_HTTP_TIMEOUT = aiohttp.ClientTimeout(total=60, connect=10)

# Open Icecat throttles free accounts and answers 429 without warning. The
# enrichment cron drains its backlog by re-enqueuing itself, so slowing the
# client down costs nothing but keeps the account out of trouble.
ICECAT_REQUESTS_PER_MINUTE = 60

# Process-wide: one enrichment batch runs 50 lookups back to back.
_RATE_LIMITER = AsyncRateLimiter(ICECAT_REQUESTS_PER_MINUTE)


def icecat_credentials_present() -> bool:
    """Both Icecat secrets hold a real value (not the example placeholder)."""
    return secret_is_set(settings.ICECAT_USERNAME) and secret_is_set(
        settings.ICECAT_API_KEY
    )


class IcecatService:
    """Service for interacting with Icecat API"""

    def __init__(self):
        # Use Open Icecat API (free tier)
        # For Full Icecat, use: https://live.icecat.biz/api
        """Initialize the icecat service instance."""
        self.base_url = "https://live.icecat.biz/api"
        # Runtime settings (R5), refreshed before each request: nothing is
        # captured at import, a change in the back-office applies at once.
        self._language: str | None = None
        self._use_open: bool | None = None

    @property
    def username(self) -> str | None:
        return settings.ICECAT_USERNAME

    @property
    def api_key(self) -> str | None:
        return settings.ICECAT_API_KEY

    @property
    def language(self) -> str:
        return self._language or settings.ICECAT_LANGUAGE or "fr"

    @property
    def use_open_icecat(self) -> bool:
        if self._use_open is not None:
            return self._use_open
        return bool(getattr(settings, "ICECAT_USE_OPEN", True))

    async def refresh_settings(self) -> None:
        """Read the language and the Open / Full choice from the registry."""
        from app.core import runtime_settings

        try:
            values = await runtime_settings.get_many(
                ["icecat_language", "icecat_use_open"]
            )
        except Exception:  # noqa: BLE001 - keep the last known values
            logger.warning("Icecat: runtime settings unreadable, keeping defaults")
            return
        self._language = values["icecat_language"]
        self._use_open = values["icecat_use_open"]

    async def _make_api_request(
        self, endpoint: str, params: dict | None = None
    ) -> dict[str, Any]:
        """Make authenticated request to Icecat API"""
        await self.refresh_settings()

        # Check if credentials are configured
        if not self.username or not self.api_key:
            raise Exception(
                "Icecat credentials not configured. Please set ICECAT_USERNAME and ICECAT_API_KEY in environment variables."
            )

        headers = {
            "Accept": "application/json",
            "Accept-Language": self.language,
        }

        # Icecat uses HTTP Basic Authentication
        auth = aiohttp.BasicAuth(self.username, self.api_key)

        # Add mandatory parameters - UserName and lang are ALWAYS required
        if params is None:
            params = {}

        params["UserName"] = self.username
        params["lang"] = self.language

        # Full Icecat requires app_key as query parameter (Open Icecat uses Basic Auth only)
        if not self.use_open_icecat and self.api_key:
            params["app_key"] = self.api_key

        url = f"{self.base_url}{endpoint}"

        logger.debug(f"Making Icecat API request to: {url}")
        # Parameter names only, never their values (audit 2026-11 + CodeQL):
        # app_key and the account name would reach Sentry and the log files.
        logger.debug("Icecat parameters: %s", ", ".join(sorted(params)))
        logger.debug(f"Using Open Icecat: {self.use_open_icecat}")

        async def _attempt() -> dict[str, Any]:
            async with aiohttp.ClientSession(timeout=_HTTP_TIMEOUT) as session:
                async with session.get(
                    url, headers=headers, params=params, auth=auth
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    error_text = await response.text()
                    if response.status == 403:
                        # Not retryable: a missing entitlement will not appear
                        # on a second call, and the caller stamps the product
                        # so it is not looked up again for a week.
                        if self.use_open_icecat and "app_key" in error_text.lower():
                            # Full Icecat only — out of scope, not an error
                            logger.debug(
                                f"Product not available in Open Icecat (Full Icecat only): {url}"
                            )
                        else:
                            logger.error(f"Icecat API Forbidden (403): {error_text}")
                        raise Exception("Icecat API access denied: 403 Forbidden")
                    if response.status in RETRYABLE_STATUSES:
                        raise RetryableHTTPError(
                            response.status,
                            f"Icecat API request failed: {response.status} - {error_text}",
                            retry_after=parse_retry_after(
                                response.headers.get("Retry-After")
                            ),
                        )
                    logger.error(
                        f"Icecat API request failed: {response.status} - {error_text}"
                    )
                    raise Exception(f"Icecat API request failed: {response.status}")

        return await request_with_retry(
            _attempt,
            description=f"Icecat GET {endpoint}",
            rate_limiter=_RATE_LIMITER,
        )

    def _extract_product_data(
        self,
        data: dict[str, Any],
        ean: str | None = None,
        brand: str | None = None,
        mpn: str | None = None,
    ) -> IcecatProductData:
        """
        Extract and structure product data from Icecat API response

        Args:
            data: Raw data from Icecat API response
            ean: EAN code (if searching by EAN)
            brand: Brand name (if searching by brand+MPN)
            mpn: Manufacturer part number (if searching by brand+MPN)

        Returns:
            Structured IcecatProductData object
        """

        if not data:
            raise ValueError("No data provided to extract product information.")

        product_data = data.get("GeneralInfo", {})
        specs_data = data.get("FeaturesGroups", [])

        # Extract EAN if not provided and available in response
        if not ean and "EANCode" in product_data:
            ean = product_data["EANCode"]

        # Extract brand if not provided
        if not brand:
            brand = product_data.get("Brand", "")

        # Extract MPN if not provided
        if not mpn:
            mpn = product_data.get("BrandPartCode", "")

        # Extract images with all available resolutions
        images = []
        if "Gallery" in data:
            for img in data["Gallery"]:
                # Each image in Gallery has multiple resolutions
                image_entry = {}

                # High resolution (3000x3000 typically)
                if "HighPic" in img:
                    image_entry["high"] = {
                        "url": img["HighPic"],
                        "size": img.get("HighPicSize", ""),
                        "width": img.get("HighPicWidth", ""),
                        "height": img.get("HighPicHeight", ""),
                    }

                # Medium resolution (500x500)
                if "Pic500x500" in img:
                    image_entry["medium"] = {
                        "url": img["Pic500x500"],
                        "size": img.get("Pic500x500Size", ""),
                        "width": img.get("Pic500x500Width", "500"),
                        "height": img.get("Pic500x500Height", "500"),
                    }

                # Low resolution (200x200)
                if "LowPic" in img:
                    image_entry["low"] = {
                        "url": img["LowPic"],
                        "size": img.get("LowPicSize", ""),
                        "width": img.get("LowPicWidth", "200"),
                        "height": img.get("LowPicHeight", "200"),
                    }

                # Thumbnail
                if "ThumbPic" in img:
                    image_entry["thumb"] = {
                        "url": img["ThumbPic"],
                        "size": img.get("ThumbPicSize", ""),
                    }

                if image_entry:
                    images.append(image_entry)

        # Fallback to single image from GeneralInfo if no Gallery
        if not images and "Image" in product_data:
            img = product_data["Image"]
            image_entry = {}

            # Check if it's a dict with resolutions or just a string URL
            if isinstance(img, dict):
                if "HighPic" in img:
                    image_entry["high"] = {
                        "url": img["HighPic"],
                        "size": img.get("HighPicSize", ""),
                        "width": img.get("HighPicWidth", ""),
                        "height": img.get("HighPicHeight", ""),
                    }
                if "Pic500x500" in img:
                    image_entry["medium"] = {
                        "url": img["Pic500x500"],
                        "size": img.get("Pic500x500Size", ""),
                        "width": img.get("Pic500x500Width", "500"),
                        "height": img.get("Pic500x500Height", "500"),
                    }
                if "LowPic" in img:
                    image_entry["low"] = {
                        "url": img["LowPic"],
                        "size": img.get("LowPicSize", ""),
                        "width": img.get("LowPicWidth", "200"),
                        "height": img.get("LowPicHeight", "200"),
                    }
                if "ThumbPic" in img:
                    image_entry["thumb"] = {
                        "url": img["ThumbPic"],
                        "size": img.get("ThumbPicSize", ""),
                    }
            else:
                # Old format: just a URL string
                image_entry["url"] = img

            if image_entry:
                images.append(image_entry)

        # Extract specifications
        specifications = []
        for group in specs_data:
            group_name = group.get("FeatureGroup", {}).get("Name", {}).get("Value", "")
            for feature in group.get("Features", []):
                feature_info = feature.get("Feature", {})
                specifications.append(
                    {
                        "group": group_name,
                        "name": feature_info.get("Name", {}).get("Value", ""),
                        "value": feature.get("Value", ""),
                        "unit": feature.get("Sign", ""),
                    }
                )

        # Extract features bullet points
        features = []
        if "BulletPoints" in data:
            for bullet in data["BulletPoints"]:
                features.append(bullet.get("Value", ""))

        # Physical dimensions from ProductSizeAndWeight (mm → cm, g → kg).
        # Falls back to None when the field is absent or not parseable.
        size_weight = product_data.get("ProductSizeAndWeight") or {}

        def _safe_float(value: Any) -> float | None:
            try:
                return float(value) if value not in (None, "", 0) else None
            except (TypeError, ValueError):
                return None

        raw_weight_g = _safe_float(size_weight.get("Weight"))
        weight_kg = raw_weight_g / 1000.0 if raw_weight_g is not None else None

        raw_depth_mm = _safe_float(size_weight.get("Depth"))
        raw_width_mm = _safe_float(size_weight.get("Width"))
        raw_height_mm = _safe_float(size_weight.get("Height"))

        length_cm = raw_depth_mm / 10.0 if raw_depth_mm is not None else None
        width_cm = raw_width_mm / 10.0 if raw_width_mm is not None else None
        height_cm = raw_height_mm / 10.0 if raw_height_mm is not None else None

        return IcecatProductData(
            icecat_id=str(product_data.get("IcecatId", None)),
            ean=ean,
            brand=brand,
            product_name=product_data.get("Title", ""),
            description=product_data.get("Description", {}).get("ShortDesc", ""),
            long_description=product_data.get("Description", {}).get("LongDesc", ""),
            category=product_data.get("Category", {}).get("Name", {}).get("Value", ""),
            images=images,
            specifications=specifications,
            features=features,
            manufacturer_code=mpn,
            release_date=product_data.get("ReleaseDate", None),
            end_of_life_date=product_data.get("EndOfLifeDate", None),
            brand_logo_url=product_data.get("BrandLogo", None),
            image_url=images[0]["medium"]["url"]
            if images and "medium" in images[0]
            else None,
            weight_kg=weight_kg,
            dimensions_length_cm=length_cm,
            dimensions_width_cm=width_cm,
            dimensions_height_cm=height_cm,
        )

    async def get_product_by_ean(self, ean: str) -> IcecatProductData | None:
        """
        Get product data by EAN/UPC code

        Args:
            ean: EAN or UPC barcode

        Returns:
            Product data or None if not found
        """
        logger.info(f"Fetching Icecat product data for EAN: {ean}")

        try:
            # Icecat uses 'gtin' parameter (Global Trade Item Number) for EAN/UPC codes
            params = {"gtin": ean}
            response = await self._make_api_request("/", params=params)

            if not response or "data" not in response:
                logger.warning(f"No Icecat data found for EAN: {ean}")
                return None

            data = response["data"]
            product = self._extract_product_data(data, ean=ean)

            logger.info(f"Successfully fetched Icecat data for: {product.product_name}")
            return product

        except Exception as e:
            logger.error(f"Failed to fetch Icecat product data for EAN {ean}: {e}")
            return None

    async def get_product_by_upc(self, upc: str) -> IcecatProductData | None:
        """
        Get product data by UPC code

        UPC-A codes (12 digits) are automatically converted to EAN-13 by adding a leading zero.
        UPC codes are compatible with Icecat's EAN search.

        Args:
            upc: UPC barcode (12 or 13 digits)

        Returns:
            Product data or None if not found
        """
        # Convert UPC-A (12 digits) to EAN-13 (13 digits) by adding leading zero
        if len(upc) == 12 and upc.isdigit():
            ean = "0" + upc
            logger.info(f"Converting UPC-A {upc} to EAN-13 {ean}")
        else:
            ean = upc

        # Use the EAN search method
        return await self.get_product_by_ean(ean)

    async def get_product_by_brand_mpn(
        self, brand: str, mpn: str
    ) -> IcecatProductData | None:
        """
        Get product data by brand and manufacturer part number

        Args:
            brand: Product brand/manufacturer
            mpn: Manufacturer part number

        Returns:
            Product data or None if not found
        """
        logger.info(f"Fetching Icecat product data for {brand} - {mpn}")

        try:
            # Icecat uses 'Brand' and 'ProductCode' parameters (case-sensitive)
            params = {"Brand": brand, "ProductCode": mpn}
            response = await self._make_api_request("/", params=params)

            if not response or "data" not in response:
                logger.warning(f"No Icecat data found for {brand} - {mpn}")
                return None

            data = response["data"]
            product = self._extract_product_data(data, brand=brand, mpn=mpn)

            logger.info(f"Successfully fetched Icecat data for: {product.product_name}")
            return product

        except Exception as e:
            if "403" in str(e):
                logger.debug(f"Product not in Icecat scope for {brand} - {mpn}: {e}")
            else:
                logger.error(
                    f"Failed to fetch Icecat product data for {brand} - {mpn}: {e}"
                )
            return None

    async def enrich_product_with_icecat(
        self,
        vendor_part_number: str | None = None,
        manufacturer: str | None = None,
        ean: str | None = None,
        upc: str | None = None,
    ) -> IcecatProductData | None:
        """
        Enrich product data with Icecat information

        Args:
            vendor_part_number: Manufacturer part number
            manufacturer: Product manufacturer/brand
            ean: Optional EAN/UPC code

        Returns:
            Dictionary with enriched product data or None if not found
        """
        logger.info(
            f"Enriching product data with Icecat: {manufacturer} - {vendor_part_number} (EAN: {ean}, UPC: {upc})"
        )

        icecat_data = None

        # Try EAN first if available
        if ean:
            icecat_data = await self.get_product_by_ean(ean)
        elif upc:
            icecat_data = await self.get_product_by_upc(upc)
        else:
            # Fallback to brand + MPN
            icecat_data = await self.get_product_by_brand_mpn(
                manufacturer, vendor_part_number
            )

        if icecat_data:
            return icecat_data
        else:
            logger.warning(
                f"No Icecat data found for {manufacturer} - {vendor_part_number}"
            )
        return None


# Singleton instance
icecat_service = IcecatService()
