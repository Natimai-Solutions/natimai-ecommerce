"""
Ingram Micro supplier integration.

Contains both the low-level REST client (``IngramMicroService`` — OAuth + HTTP
via aiohttp, no SDK) and the :class:`SupplierAdapter` wrapper that normalizes
Ingram payloads into the supplier-agnostic DTOs.
"""
# mypy: disable-error-code="arg-type,assignment,misc,no-any-return,no-untyped-call,no-untyped-def,override,return-value,type-arg,valid-type"

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import aiohttp
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.suppliers.base import (
    NormalizedPricing,
    NormalizedProductData,
    SupplierAdapter,
    SupplierHealth,
)

logger = logging.getLogger(__name__)

INGRAM_URL = "https://api.ingrammicro.com:443"


class IngramProductData(BaseModel):
    """Model for Ingram Micro product data (raw shape from the catalog API)."""

    sku: str = Field(description="Ingram Micro SKU")
    vendor_part_number: str = Field(description="Manufacturer part number")
    manufacturer: str = Field(description="Product manufacturer")
    product_name: str = Field(description="Product name")
    description: str | None = Field(default=None, description="Product description")
    category: str = Field(description="Product category")
    subcategory: str | None = Field(default=None, description="Product subcategory")
    price: float = Field(description="Unit price")
    availability: int = Field(description="Available quantity")
    weight: float | None = Field(default=None, description="Product weight")
    dimensions: dict[str, float] | None = Field(
        default=None, description="Product dimensions"
    )
    image_url: str | None = Field(default=None, description="Product image URL")
    specification_url: str | None = Field(
        default=None, description="Product specification URL"
    )
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    upc_code: str | None = Field(default=None, description="Product UPC code")
    ean: str | None = Field(default=None, description="Product EAN code")


class IngramMicroService:
    """Low-level client for the Ingram Micro REST API."""

    def __init__(self) -> None:
        # Ingram Micro sandbox uses /sandbox prefix in the path
        """Initialize the ingram micro service instance."""
        if settings.INGRAM_ENVIRONMENT == "sandbox":
            self.base_url = f"{INGRAM_URL}/sandbox"
        else:
            self.base_url = INGRAM_URL
        self.client_id = settings.INGRAM_CLIENT_ID
        self.client_secret = settings.INGRAM_CLIENT_SECRET
        self.customer_number = settings.INGRAM_CUSTOMER_NUMBER
        self.access_token: str | None = None
        self.token_expires_at: datetime | None = None

    async def _get_access_token(self) -> str:
        """Get or refresh OAuth access token"""
        if (
            self.access_token
            and self.token_expires_at
            and datetime.now(timezone.utc) < self.token_expires_at
        ):
            return self.access_token

        logger.debug("Obtaining new Ingram Micro access token")

        auth_url = f"{INGRAM_URL}/oauth/oauth20/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(auth_url, headers=headers, data=data) as response:
                if response.status == 200:
                    token_data = await response.json()
                    self.access_token = token_data["access_token"]
                    expires_in = int(token_data.get("expires_in", 3600))
                    self.token_expires_at = datetime.now(timezone.utc).replace(
                        second=0, microsecond=0
                    ) + timedelta(seconds=expires_in - 300)  # 5 min buffer

                    logger.debug("Successfully obtained Ingram Micro access token")
                    return self.access_token
                else:
                    error_text = await response.text()
                    logger.error(
                        f"Failed to get access token: {response.status} - {error_text}"
                    )
                    raise Exception(f"Authentication failed: {response.status}")

    async def _make_api_request(
        self, endpoint: str, params: dict | None = None
    ) -> dict[str, Any]:
        """Make authenticated request to Ingram Micro API"""
        access_token = await self._get_access_token()

        # Generate correlation ID limited to 32 characters (UUID without hyphens, truncated)
        correlation_id = str(uuid4()).replace("-", "")[:32]

        headers = {
            "Authorization": f"Bearer {access_token}",
            "IM-CustomerNumber": self.customer_number,
            "IM-CountryCode": settings.INGRAM_COUNTRY_CODE,
            "IM-CorrelationID": correlation_id,
            "IM-SenderID": "FastAPI-Ecommerce",  # Optional but recommended
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Language": "en",  # Default language
        }

        url = f"{self.base_url}{endpoint}"

        logger.debug(f"Making API request to: {url}")
        logger.debug(f"Parameters: {params}")

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                logger.debug(f"Final URL with params: {response.url}")
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logger.error(
                        f"API request failed: {response.status} - {error_text}"
                    )
                    raise Exception(f"API request failed: {response.status}")

    async def _make_api_post_request(
        self,
        endpoint: str,
        body: dict[str, Any],
        params: dict[str, str] | None = None,
        expected_statuses: list[int] | None = None,
    ) -> dict[str, Any]:
        """Make authenticated POST request to Ingram Micro API with optional query parameters"""
        if expected_statuses is None:
            expected_statuses = [200]

        access_token = await self._get_access_token()

        correlation_id = str(uuid4()).replace("-", "")[:32]

        headers = {
            "Authorization": f"Bearer {access_token}",
            "IM-CustomerNumber": self.customer_number,
            "IM-CountryCode": settings.INGRAM_COUNTRY_CODE,
            "IM-CorrelationID": correlation_id,
            "IM-SenderID": "FastAPI-Ecommerce",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Language": "en",
        }

        url = f"{self.base_url}{endpoint}"

        logger.debug(f"Making POST API request to: {url}")
        if params:
            logger.debug(f"Query params: {params}")
        logger.debug(f"Request body: {body}")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, headers=headers, json=body, params=params
            ) as response:
                logger.debug(f"Final URL with params: {response.url}")
                if response.status in expected_statuses:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logger.error(
                        f"API POST request failed: {response.status} - {error_text}"
                    )
                    raise Exception(f"API request failed: {response.status}")

    async def create_purchase_order(
        self,
        customer_order_number: str,
        lines: list[dict[str, Any]],
        ship_to: dict[str, Any],
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Submit a purchase order to Ingram Micro (POST /resellers/v6/orders).

        ``customer_order_number`` is echoed back in the response and used by Ingram
        for deduplication — always pass the local order UUID so retries are safe.
        ``lines`` items must contain ``ingramPartNumber`` and ``quantity``; ``unitPrice``
        is optional (Ingram falls back to the contracted price when omitted).
        """
        numbered_lines = [{"lineNumber": i + 1, **line} for i, line in enumerate(lines)]
        body: dict[str, Any] = {
            "customerOrderNumber": customer_order_number[:35],
            "shipToInfo": ship_to,
            "lines": numbered_lines,
        }
        if notes:
            body["notes"] = notes

        logger.info(
            "Creating Ingram Micro PO: customerOrderNumber=%s lines=%d",
            customer_order_number,
            len(lines),
        )
        return await self._make_api_post_request(
            "/resellers/v6/orders",
            body,
            expected_statuses=[200, 201],
        )

    async def get_product_catalog(
        self,
        category: str | None = None,
        vendors: list | None = None,
        page_number: int = 1,
        page_size: int = 25,
    ) -> list[IngramProductData]:
        """Retrieve a page of the product catalog from Ingram Micro."""
        logger.debug(
            f"Fetching product catalog - category: {category}, page: {page_number}"
        )

        params = {"pageNumber": page_number, "pageSize": min(page_size, 100)}
        if category:
            params["category"] = category
        if vendors:
            params["vendor"] = vendors

        try:
            response = await self._make_api_request("/resellers/v6/catalog", params)

            products: list[IngramProductData] = []

            if isinstance(response, list):
                catalog_data = response
            elif isinstance(response, dict):
                catalog_data = response.get(
                    "catalog", response.get("products", response.get("data", []))
                )
            else:
                logger.error(f"Unexpected response type: {type(response)}")
                catalog_data = []

            for i, item in enumerate(catalog_data):
                try:
                    if isinstance(item, list) and len(item) > 0:
                        item = item[0]
                    if not isinstance(item, dict):
                        logger.error(f"Item {i} is not a dict: {type(item)}")
                        continue

                    product = IngramProductData(
                        sku=item.get("ingramPartNumber", ""),
                        vendor_part_number=item.get("vendorPartNumber", ""),
                        manufacturer=item.get("vendorName", ""),
                        product_name=item.get("description", ""),
                        description=item.get("extraDescription"),
                        category=item.get("category", ""),
                        subcategory=item.get("subCategory"),
                        price=0.0,  # Not available in catalog endpoint
                        availability=0,  # Not available in catalog endpoint
                        weight=None,
                        dimensions=None,
                        image_url=None,
                        specification_url=None,
                        upc_code=item.get("upcCode"),
                    )
                    products.append(product)
                except Exception as e:
                    logger.error(f"Error parsing product data: {e}")
                    continue

            logger.debug(f"Successfully fetched {len(products)} products")
            return products

        except Exception as e:
            logger.error(f"Failed to fetch product catalog: {e}")
            raise

    async def get_price_and_availability(
        self,
        skus: list[str],
        include_pricing: bool = True,
        include_availability: bool = True,
    ) -> dict[str, dict[str, Any]]:
        """Get price and availability for specific SKUs (max 50 per request)."""
        logger.info(f"Fetching price and availability for {len(skus)} SKUs")

        skus_to_check = skus[:50]
        request_body = {
            "products": [{"ingramPartNumber": sku} for sku in skus_to_check]
        }
        params = {
            "includePricing": "true" if include_pricing else "false",
            "includeAvailability": "true" if include_availability else "false",
            "includeProductAttributes": "false",
        }

        try:
            response = await self._make_api_post_request(
                "/resellers/v6/catalog/priceandavailability", request_body, params
            )

            results: dict[str, dict[str, Any]] = {}

            if isinstance(response, list):
                products_data = response
            elif isinstance(response, dict):
                products_data = response.get(
                    "data", response.get("products", response.get("catalog", []))
                )
            else:
                logger.error(f"Unexpected response type: {type(response)}")
                products_data = []

            for item in products_data:
                sku = item.get("ingramPartNumber")
                if not sku:
                    continue

                pricing_info = {}
                if include_pricing and "pricing" in item:
                    pricing = item["pricing"]
                    pricing_info = {
                        "customer_price": pricing.get("customerPrice", 0),
                        "retail_price": pricing.get("retailPrice", 0),
                        "currency": pricing.get("currencyCode", "USD"),
                    }

                availability_info = {}
                if include_availability and "availability" in item:
                    availability = item["availability"]
                    total_qty = 0
                    for warehouse in availability.get("availabilityByWarehouse", []):
                        qty = warehouse.get("quantityAvailable", 0)
                        if isinstance(qty, int | float):
                            total_qty += int(qty)
                    availability_info = {
                        "total_quantity": total_qty,
                        "warehouses": availability.get("availabilityByWarehouse", []),
                    }

                results[sku] = {
                    **pricing_info,
                    **availability_info,
                    "vendor_part_number": item.get("vendorPartNumber"),
                    "vendor_name": item.get("vendorName"),
                }

            logger.info(f"Successfully fetched data for {len(results)} SKUs")
            return results

        except Exception as e:
            logger.error(f"Failed to fetch price and availability: {e}")
            raise


def _to_normalized_product(item: IngramProductData) -> NormalizedProductData:
    """Execute to normalized product."""
    return NormalizedProductData(
        supplier_sku=item.sku,
        name=item.product_name,
        manufacturer=item.manufacturer or None,
        vendor_part_number=item.vendor_part_number or None,
        description=item.description,
        category=item.category or None,
        subcategory=item.subcategory,
        price=item.price,
        quantity=item.availability,
        currency=None,
        weight=item.weight,
        image_url=item.image_url,
        spec_url=item.specification_url,
        upc=item.upc_code,
        ean=item.ean,
    )


class IngramMicroAdapter(SupplierAdapter):
    """Supplier adapter wrapping :class:`IngramMicroService`."""

    name = "ingram_micro"
    display_name = "Ingram Micro"
    price_batch_size = 50

    def __init__(self, service: IngramMicroService | None = None) -> None:
        """Initialize the ingram micro adapter instance."""
        self._service = service

    @property
    def service(self) -> IngramMicroService:
        # Built lazily so importing the module never triggers config access.
        """Execute service."""
        if self._service is None:
            self._service = IngramMicroService()
        return self._service

    # -- configuration ----------------------------------------------------

    @property
    def default_categories(self) -> list[str]:  # type: ignore[override]
        """Execute default categories."""
        return list(settings.INGRAM_SYNC_CATEGORIES)

    def is_configured(self) -> bool:
        """Check whether configured."""
        return all(
            [
                settings.INGRAM_CLIENT_ID,
                settings.INGRAM_CLIENT_SECRET,
                settings.INGRAM_CUSTOMER_NUMBER,
            ]
        )

    def is_sync_enabled(self) -> bool:
        """Check whether sync enabled."""
        return bool(settings.INGRAM_SYNC_ENABLED)

    def sync_interval_hours(self) -> int:
        """Synchronize interval hours."""
        return int(settings.INGRAM_SYNC_INTERVAL_HOURS)

    def config_summary(self) -> dict[str, Any]:
        """Execute config summary."""
        summary = super().config_summary()
        summary.update(
            {
                "environment": settings.INGRAM_ENVIRONMENT,
                "country_code": settings.INGRAM_COUNTRY_CODE,
                "sync_interval_hours": self.sync_interval_hours(),
            }
        )
        return summary

    # -- catalog ----------------------------------------------------------

    async def fetch_catalog(
        self, category: str, **filters: Any
    ) -> AsyncIterator[list[NormalizedProductData]]:
        """Execute fetch catalog."""
        page = 1
        page_size = int(filters.get("page_size", 100))
        vendors = filters.get("vendors")
        while True:
            products = await self.service.get_product_catalog(
                category=category,
                vendors=vendors,
                page_number=page,
                page_size=page_size,
            )
            if not products:
                break
            yield [_to_normalized_product(p) for p in products]
            page += 1

    async def fetch_price_and_availability(
        self, skus: list[str]
    ) -> dict[str, NormalizedPricing]:
        """Execute fetch price and availability."""
        if not skus:
            return {}
        raw = await self.service.get_price_and_availability(
            skus=skus[: self.price_batch_size],
            include_pricing=True,
            include_availability=True,
        )
        result: dict[str, NormalizedPricing] = {}
        for sku, data in raw.items():
            result[sku] = NormalizedPricing(
                supplier_sku=sku,
                price=data.get("customer_price", 0),
                currency=data.get("currency", "USD"),
                quantity=data.get("total_quantity", 0),
                vendor_part_number=data.get("vendor_part_number"),
                manufacturer=data.get("vendor_name"),
                extra={"warehouses": data.get("warehouses", [])},
            )
        return result

    # -- health -----------------------------------------------------------

    async def health_check(self) -> SupplierHealth:
        """Execute health check."""
        if not self.is_configured():
            return SupplierHealth(
                healthy=False,
                configured=False,
                message="Ingram Micro credentials not configured",
            )
        if not self.is_sync_enabled():
            return SupplierHealth(
                healthy=False,
                configured=True,
                message="Ingram Micro synchronization is disabled in settings",
            )
        try:
            categories = self.default_categories or ["Ordinateur/Serveur"]
            products = await self.service.get_product_catalog(
                category=categories[0], page_number=1, page_size=1
            )
            return SupplierHealth(
                healthy=True,
                configured=True,
                message=f"API is responsive. Test call returned {len(products)} products.",
                details={"test_products": len(products)},
            )
        except Exception as e:  # noqa: BLE001 - surfaced to the caller
            return SupplierHealth(
                healthy=False,
                configured=True,
                message=f"API connectivity test failed: {e}",
            )
