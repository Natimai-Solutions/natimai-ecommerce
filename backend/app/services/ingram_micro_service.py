"""
Service for Ingram Micro REST API integration.
Handles product catalog synchronization and inventory management using direct HTTP calls.
No SDK dependency - uses aiohttp for OAuth and API requests.
"""
# mypy: disable-error-code="arg-type,assignment,no-any-return,no-untyped-call,no-untyped-def,return-value,type-arg,valid-type"

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import aiohttp
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings

logger = logging.getLogger(__name__)


class IngramProductData(BaseModel):
    """Model for Ingram Micro product data"""

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


INGRAM_URL = "https://api.ingrammicro.com:443"


class IngramMicroService:
    """Service for interacting with Ingram Micro API"""

    def __init__(self):
        # Ingram Micro sandbox uses /sandbox prefix in the path
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

        # Log request details for debugging
        logger.debug(f"Making API request to: {url}")
        logger.debug(f"Parameters: {params}")
        logger.debug(f"Customer Number: {self.customer_number}")
        logger.debug(f"Country Code: {settings.INGRAM_COUNTRY_CODE}")
        logger.debug(f"Environment: {settings.INGRAM_ENVIRONMENT}")

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                # Log the actual URL with query parameters
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
        self, endpoint: str, body: dict[str, Any], params: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Make authenticated POST request to Ingram Micro API with optional query parameters"""
        access_token = await self._get_access_token()

        # Generate correlation ID limited to 32 characters
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
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logger.error(
                        f"API POST request failed: {response.status} - {error_text}"
                    )
                    raise Exception(f"API request failed: {response.status}")

    async def get_product_catalog(
        self,
        category: str | None = None,
        vendors: list | None = None,
        page_number: int = 1,
        page_size: int = 25,
    ) -> list[IngramProductData]:
        """
        Retrieve product catalog from Ingram Micro

        Args:
            category: Product category filter
            page_number: Page number for pagination
            page_size: Number of products per page (max 100)

        Returns:
            List of product data
        """
        logger.debug(
            f"Fetching product catalog - category: {category}, page: {page_number}"
        )

        # Use parameters that are more likely to return results
        params = {"pageNumber": page_number, "pageSize": min(page_size, 100)}

        # Add category if provided
        if category:
            params["category"] = category

        if vendors:
            params["vendor"] = vendors

        try:
            # Using catalog endpoint for sandbox
            response = await self._make_api_request("/resellers/v6/catalog", params)

            # Log the response structure for debugging
            logger.debug(f"API Response type: {type(response)}")
            logger.debug(
                f"API Response keys: {list(response.keys()) if isinstance(response, dict) else 'Not a dict'}"
            )

            products = []

            # Handle different response structures
            if isinstance(response, list):
                # Response is directly a list of products
                catalog_data = response
            elif isinstance(response, dict):
                # Response is a dict, try to find the products array
                catalog_data = response.get(
                    "catalog", response.get("products", response.get("data", []))
                )
            else:
                logger.error(f"Unexpected response type: {type(response)}")
                catalog_data = []

            logger.debug(f"Catalog data type: {type(catalog_data)}")
            logger.debug(
                f"Number of items in catalog: {len(catalog_data) if catalog_data else 0}"
            )

            for i, item in enumerate(catalog_data):
                try:
                    logger.debug(f"Item {i} content: {item}")

                    # Handle if item is a list instead of dict
                    if isinstance(item, list) and len(item) > 0:
                        # Use the first element if it's a list
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
                        subcategory=item.get(
                            "subCategory"
                        ),  # Note: subCategory with capital C
                        price=0.0,  # Price not available in catalog endpoint
                        availability=0,  # Availability not available in catalog endpoint
                        weight=None,  # Weight not available in catalog endpoint
                        dimensions=None,  # Dimensions not available in catalog endpoint
                        image_url=None,  # Image URL not available in catalog endpoint
                        specification_url=None,  # Spec URL not available in catalog endpoint
                        upc_code=item.get("upcCode"),  # Note: upcCode with capital C
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
        """
        Get price and availability information for specific SKUs using POST endpoint

        Args:
            skus: List of Ingram Micro part numbers (max 50 per request)
            include_pricing: Include pricing information
            include_availability: Include availability information

        Returns:
            Dictionary mapping SKU to price and availability data
        """
        logger.info(f"Fetching price and availability for {len(skus)} SKUs")

        # Limit to 50 SKUs per request as per API documentation
        skus_to_check = skus[:50]

        # Build request body - only products list
        request_body = {
            "products": [{"ingramPartNumber": sku} for sku in skus_to_check]
        }

        # Build query parameters - includePricing and includeAvailability go here
        params = {
            "includePricing": "true" if include_pricing else "false",
            "includeAvailability": "true" if include_availability else "false",
            "includeProductAttributes": "false",
        }

        try:
            response = await self._make_api_post_request(
                "/resellers/v6/catalog/priceandavailability", request_body, params
            )

            # Log response structure for debugging
            logger.debug(f"Price/Availability Response type: {type(response)}")
            if isinstance(response, dict):
                logger.debug(f"Response keys: {list(response.keys())}")

            results = {}

            # Handle different response structures
            if isinstance(response, list):
                # Response is directly a list of products
                products_data = response
            elif isinstance(response, dict):
                # Response is a dict, try to find the products array
                products_data = response.get(
                    "data", response.get("products", response.get("catalog", []))
                )
            else:
                logger.error(f"Unexpected response type: {type(response)}")
                products_data = []

            logger.debug(f"Number of products in response: {len(products_data)}")

            # Parse response
            for item in products_data:
                sku = item.get("ingramPartNumber")
                if not sku:
                    continue

                # Extract pricing information
                pricing_info = {}
                if include_pricing and "pricing" in item:
                    pricing = item["pricing"]
                    pricing_info = {
                        "customer_price": pricing.get("customerPrice", 0),
                        "retail_price": pricing.get("retailPrice", 0),
                        "currency": pricing.get("currencyCode", "USD"),
                    }

                # Extract availability information
                availability_info = {}
                if include_availability and "availability" in item:
                    availability = item["availability"]
                    total_qty = 0

                    # Sum quantities from all warehouses
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

    def _convert_ingram_to_product_create(
        self, ingram_product: IngramProductData
    ) -> dict[str, any]:
        """Convert Ingram product data to Product creation data using generic supplier fields"""
        return {
            "name": ingram_product.product_name,
            "description": ingram_product.description
            or f"{ingram_product.manufacturer} {ingram_product.product_name}",
            # "supplier_price": Decimal(str(ingram_product.price or 0.0)),
            # "base_price": Decimal(str(ingram_product.price or 0.0)), # TODO: Review pricing strategy
            "has_variants": False,
            # Generic supplier fields
            "supplier_sku": ingram_product.sku,
            "vendor_part_number": ingram_product.vendor_part_number,
            "manufacturer": ingram_product.manufacturer,
            "supplier_name": "Ingram Micro",  # Specific supplier identifier
            "supplier_category": ingram_product.category,
            "supplier_subcategory": ingram_product.subcategory,
            "weight": ingram_product.weight,
            "supplier_image_url": ingram_product.image_url,
            "supplier_spec_url": ingram_product.specification_url,
            # "last_supplier_sync": ingram_product.last_updated.isoformat(), #Sync is for inventory and pricing only
            "is_supplier_managed": True,
            "is_active": True,
            "upc": ingram_product.upc_code,
        }

    async def _upsert_product(
        self, session: AsyncSession, ingram_product: IngramProductData
    ) -> dict[str, any]:
        """Insert or update a product from Ingram data"""
        from app.features.product.crud.product import crud_product
        from app.features.product.models.product import ProductCreate, ProductUpdate

        # Check if product already exists by supplier SKU and Ingram Micro supplier name
        existing_product = await crud_product.get_by_supplier_sku(
            session=session,
            supplier_sku=ingram_product.sku,
            supplier_name="Ingram Micro",
        )

        product_data_dict = self._convert_ingram_to_product_create(ingram_product)

        if existing_product:
            # Update existing product - convert dict to ProductUpdate
            product_update = ProductUpdate(**product_data_dict)
            updated_product = await crud_product.update(
                session=session, id=existing_product.id, data=product_update, user=None
            )
            return {"action": "updated", "product_id": str(updated_product.id)}
        else:
            # Create new product - convert dict to ProductCreate
            product_create = ProductCreate(**product_data_dict)
            new_product = await crud_product.create(
                session=session, data=product_create, user=None
            )
            return {"action": "created", "product_id": str(new_product.id)}

    async def sync_products_to_database(
        self, session: AsyncSession, categories: list[str]
    ) -> dict[str, int]:
        """
        Synchronize products from Ingram Micro to local database

        Args:
            session: Database session
            categories: List of categories to synchronize

        Returns:
            Dictionary with sync statistics
        """
        stats = {
            "total_fetched": 0,
            "new_products": 0,
            "updated_products": 0,
            "skipped_products": 0,
            "errors": 0,
        }

        logger.debug(f"Starting product sync for categories: {categories}")

        for category in categories:
            try:
                page = 1
                page_size = 100
                while True:
                    products = await self.get_product_catalog(
                        category=category, page_number=page, page_size=page_size
                    )

                    if not products:
                        break

                    stats["total_fetched"] += len(products)

                    for product in products:
                        # Skip products with no SKU or invalid data
                        if not product.sku or not product.product_name:
                            stats["skipped_products"] += 1
                            continue

                        try:
                            result = await self._upsert_product(session, product)

                            if result["action"] == "created":
                                stats["new_products"] += 1
                            elif result["action"] == "updated":
                                stats["updated_products"] += 1

                            # Commit after each successful product to avoid transaction issues
                            await session.commit()

                        except Exception as e:
                            logger.error(f"Error syncing product {product.sku}: {e}")
                            stats["errors"] += 1
                            # Critical: Rollback to clear the failed transaction state
                            await session.rollback()
                            continue

                    page += 1

                    # For local development, limit pages to avoid long syncs
                    # if settings.ENVIRONMENT == "local" and page > 10:
                    #   break

                    # Add delay to respect rate limits
                    await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"Error syncing category {category}: {e}")
                stats["errors"] += 1

        # No final commit needed as we commit after each product
        logger.debug(f"Product sync completed. Stats: {stats}")
        return stats


# Singleton instance
ingram_service = IngramMicroService()
