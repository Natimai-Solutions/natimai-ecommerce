from typing import Any

from pydantic import BaseModel, Field


class IcecatProductData(BaseModel):
    """Model for Icecat product data"""

    icecat_id: str | None = Field(default=None, description="Icecat product ID")
    ean: str | None = Field(default=None, description="EAN/UPC barcode")
    brand: str = Field(description="Product brand/manufacturer")
    product_name: str = Field(description="Product name")
    description: str | None = Field(default=None, description="Short description")
    long_description: str | None = Field(
        default=None, description="Long product description"
    )
    category: str | None = Field(default=None, description="Product category")
    images: list[dict[str, Any]] = Field(
        default_factory=list, description="Product images"
    )
    image_url: str | None = Field(default=None, description="Main product image URL")
    specifications: list[dict[str, Any]] = Field(
        default_factory=list, description="Technical specifications"
    )
    features: list[str] = Field(
        default_factory=list, description="Product features bullet points"
    )
    manufacturer_code: str | None = Field(
        default=None, description="Manufacturer part number"
    )
    release_date: str | None = Field(default=None, description="Product release date")
    end_of_life_date: str | None = Field(
        default=None, description="Product end of life date"
    )
    brand_logo_url: str | None = Field(
        default=None, description="URL of the brand logo"
    )
