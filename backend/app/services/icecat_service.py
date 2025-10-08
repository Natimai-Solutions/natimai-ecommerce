"""
Service for Icecat API integration.
Handles product specifications, images, and technical details retrieval.
Documentation: https://iceclog.com/manual-for-icecat-json-product-requests/
"""

import logging
from typing import Any

import aiohttp
from pydantic import BaseModel, Field

from app.core.config import settings

logger = logging.getLogger(__name__)


class IcecatProductData(BaseModel):
    """Model for Icecat product data"""

    ean: str | None = Field(default=None, description="EAN/UPC barcode")
    brand: str = Field(description="Product brand/manufacturer")
    product_name: str = Field(description="Product name")
    description: str | None = Field(default=None, description="Short description")
    long_description: str | None = Field(
        default=None, description="Long product description"
    )
    category: str | None = Field(default=None, description="Product category")
    images: list[dict[str, str]] = Field(
        default_factory=list, description="Product images"
    )
    specifications: list[dict[str, Any]] = Field(
        default_factory=list, description="Technical specifications"
    )
    features: list[str] = Field(
        default_factory=list, description="Product features bullet points"
    )
    manufacturer_code: str | None = Field(
        default=None, description="Manufacturer part number"
    )


class IcecatService:
    """Service for interacting with Icecat API"""

    def __init__(self):
        self.base_url = "https://live.icecat.biz/api"
        self.username = settings.ICECAT_USERNAME
        self.api_key = settings.ICECAT_API_KEY
        self.language = settings.ICECAT_LANGUAGE or "fr"

    async def _make_api_request(
        self, endpoint: str, params: dict | None = None
    ) -> dict[str, Any]:
        """Make authenticated request to Icecat API"""

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

        # Add mandatory parameters UserName and lang
        if params is None:
            params = {}
        params["UserName"] = self.username
        params["lang"] = self.language

        url = f"{self.base_url}{endpoint}"

        logger.debug(f"Making Icecat API request to: {url}")
        logger.debug(f"Parameters: {params}")

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=headers, params=params, auth=auth
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logger.error(
                        f"Icecat API request failed: {response.status} - {error_text}"
                    )
                    raise Exception(f"Icecat API request failed: {response.status}")

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
            product_data = data.get("GeneralInfo", {})
            specs_data = data.get("FeaturesGroups", [])

            # Extract images
            images = []
            if "Gallery" in data:
                for img in data["Gallery"]:
                    images.append(
                        {
                            "url": img.get("Pic", ""),
                            "size": img.get("Size", ""),
                            "type": img.get("PicHeight", 0),
                        }
                    )
            elif "Image" in product_data:
                images.append(
                    {
                        "url": product_data["Image"],
                        "size": "main",
                        "type": "primary",
                    }
                )

            # Extract specifications
            specifications = []
            for group in specs_data:
                group_name = (
                    group.get("FeatureGroup", {}).get("Name", {}).get("Value", "")
                )
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

            product = IcecatProductData(
                ean=ean,
                brand=product_data.get("Brand", ""),
                product_name=product_data.get("Title", ""),
                description=product_data.get("Description", {}).get("ShortDesc", ""),
                long_description=product_data.get("Description", {}).get(
                    "LongDesc", ""
                ),
                category=product_data.get("Category", {})
                .get("Name", {})
                .get("Value", ""),
                images=images,
                specifications=specifications,
                features=features,
                manufacturer_code=product_data.get("BrandPartCode", ""),
            )

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
            product_data = data.get("GeneralInfo", {})

            # Extract EAN if available
            ean = None
            if "EANCode" in product_data:
                ean = product_data["EANCode"]

            # Extract images
            images = []
            if "Gallery" in data:
                for img in data["Gallery"]:
                    images.append(
                        {
                            "url": img.get("Pic", ""),
                            "size": img.get("Size", ""),
                            "type": "gallery",
                        }
                    )
            elif "Image" in product_data:
                images.append(
                    {
                        "url": product_data["Image"],
                        "size": "main",
                        "type": "primary",
                    }
                )

            # Extract specifications
            specifications = []
            specs_data = data.get("FeaturesGroups", [])
            for group in specs_data:
                group_name = (
                    group.get("FeatureGroup", {}).get("Name", {}).get("Value", "")
                )
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

            product = IcecatProductData(
                ean=ean,
                brand=brand,
                product_name=product_data.get("Title", ""),
                description=product_data.get("Description", {}).get("ShortDesc", ""),
                long_description=product_data.get("Description", {}).get(
                    "LongDesc", ""
                ),
                category=product_data.get("Category", {})
                .get("Name", {})
                .get("Value", ""),
                images=images,
                specifications=specifications,
                features=features,
                manufacturer_code=mpn,
            )

            logger.info(f"Successfully fetched Icecat data for: {product.product_name}")
            return product

        except Exception as e:
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
    ) -> dict[str, Any] | None:
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
            f"Enriching product data with Icecat: {manufacturer} - {vendor_part_number}"
        )

        # Try EAN first if available
        if ean:
            icecat_data = await self.get_product_by_ean(ean)
            if icecat_data:
                return self._convert_to_enrichment_data(icecat_data)
        elif upc:
            icecat_data = await self.get_product_by_upc(upc)
            if icecat_data:
                return self._convert_to_enrichment_data(icecat_data)
        else:
            # Fallback to brand + MPN
            icecat_data = await self.get_product_by_brand_mpn(
                manufacturer, vendor_part_number
            )
            if icecat_data:
                return self._convert_to_enrichment_data(icecat_data)

        logger.warning(
            f"No Icecat data found for {manufacturer} - {vendor_part_number}"
        )
        return None

    def _convert_to_enrichment_data(
        self, icecat_data: IcecatProductData
    ) -> dict[str, Any]:
        """Convert Icecat data to enrichment format"""
        # Get the main image URL
        main_image = None
        if icecat_data.images:
            main_image = icecat_data.images[0].get("url")

        return {
            "icecat_enriched": True,
            "long_description": icecat_data.long_description,
            "images": [img.get("url") for img in icecat_data.images if img.get("url")],
            "main_image_url": main_image,
            "specifications": icecat_data.specifications,
            "features": icecat_data.features,
            "icecat_category": icecat_data.category,
        }


# Singleton instance
icecat_service = IcecatService()
