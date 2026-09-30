"""DB-backed spec definition — editable counterpart to the original YAML catalog."""

import uuid
from datetime import datetime, timezone

from sqlmodel import JSON, Column, Field, SQLModel


class SpecDefinitionBase(SQLModel):
    """Shared fields for SpecDefinition."""

    key: str = Field(max_length=50, description="Canonical spec key, e.g. memory_gb")
    label_fr: str = Field(max_length=200, description="French display label")
    type: str = Field(max_length=10, description="Value type: numeric | enum")
    unit: str | None = Field(
        default=None, max_length=20, description="Unit for numeric specs"
    )
    categories: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON),
        description="Category slugs/keywords this spec applies to",
    )
    aliases: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON),
        description="Icecat field name aliases (case-insensitive matching)",
    )
    is_active: bool = Field(default=True)
    highlight_rank: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Position among the key-spec tiles of the product page (1 = first); "
            "None = not highlighted. The page shows the first four the product has."
        ),
    )


class SpecDefinitionCreate(SpecDefinitionBase):
    pass


class SpecDefinitionUpdate(SQLModel):
    label_fr: str | None = None
    type: str | None = None
    unit: str | None = None
    categories: list[str] | None = None
    aliases: list[str] | None = None
    is_active: bool | None = None
    highlight_rank: int | None = Field(default=None, ge=1)


class SpecDefinition(SpecDefinitionBase, table=True):
    """Persistable spec definition — one row per canonical spec key."""

    __tablename__ = "spec_definitions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SpecDefinitionPublic(SpecDefinitionBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class SpecDefinitionsPublic(SQLModel):
    data: list[SpecDefinitionPublic] = Field(default_factory=list)
    count: int = 0
