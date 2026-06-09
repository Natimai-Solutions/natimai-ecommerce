"""phase3_spec_definitions

Revision ID: c1d6e4f3a8b2
Revises: b9c5d3e2f7a1
Create Date: 2026-06-08

Creates the spec_definitions table and seeds it from the existing
spec_definitions.yaml catalog (10 computer/server specs).

After this migration, spec_projection.py can read specs from the DB
instead of the YAML file, making them editable via the admin UI.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1d6e4f3a8b2"
down_revision: str | None = "b9c5d3e2f7a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Seed data — mirrors spec_definitions.yaml Phase 1 catalog
_SEED_SPECS = [
    {
        "key": "cpu_brand",
        "label_fr": "Marque du processeur",
        "type": "enum",
        "unit": None,
        "categories": ["ordinateur", "laptop", "portable", "serveur", "workstation", "desktop", "notebook"],
        "aliases": ["marque du processeur", "processor brand", "cpu brand", "processor manufacturer", "marque processeur"],
    },
    {
        "key": "cpu_family",
        "label_fr": "Famille de processeur",
        "type": "enum",
        "unit": None,
        "categories": ["ordinateur", "laptop", "portable", "serveur", "workstation", "desktop", "notebook"],
        "aliases": ["famille de processeur", "processor family", "cpu family", "processor series", "famille processeur", "gamme processeur"],
    },
    {
        "key": "cpu_cores",
        "label_fr": "Nombre de cœurs",
        "type": "numeric",
        "unit": None,
        "categories": ["ordinateur", "laptop", "portable", "serveur", "workstation", "desktop", "notebook"],
        "aliases": ["nombre de cœurs", "number of cores", "nombre de coeurs", "cores", "cpu cores", "processor cores"],
    },
    {
        "key": "memory_gb",
        "label_fr": "Mémoire RAM (Go)",
        "type": "numeric",
        "unit": "GB",
        "categories": ["ordinateur", "laptop", "portable", "serveur", "workstation", "desktop", "notebook"],
        "aliases": ["mémoire installée", "ram", "system memory", "memory", "mémoire vive", "installed memory", "mémoire ram", "capacité mémoire", "memory capacity"],
    },
    {
        "key": "storage_gb",
        "label_fr": "Stockage (Go)",
        "type": "numeric",
        "unit": "GB",
        "categories": ["ordinateur", "laptop", "portable", "serveur", "workstation", "desktop", "notebook"],
        "aliases": ["capacité du ssd", "capacité du hdd", "total storage", "storage capacity", "capacité de stockage", "disk capacity", "drive capacity", "capacité disque", "espace disque"],
    },
    {
        "key": "storage_type",
        "label_fr": "Type de stockage",
        "type": "enum",
        "unit": None,
        "categories": ["ordinateur", "laptop", "portable", "serveur", "workstation", "desktop", "notebook"],
        "aliases": ["type de disque", "storage drive type", "type de stockage", "drive type", "storage type", "type stockage"],
    },
    {
        "key": "screen_inches",
        "label_fr": "Taille d'écran (pouces)",
        "type": "numeric",
        "unit": "inch",
        "categories": ["laptop", "portable", "notebook", "moniteur", "ecran", "display"],
        "aliases": ["taille de l'écran", "display size", "screen size", "taille écran", "diagonal", "diagonale", "screen diagonal"],
    },
    {
        "key": "gpu_brand",
        "label_fr": "Marque carte graphique",
        "type": "enum",
        "unit": None,
        "categories": ["ordinateur", "laptop", "portable", "serveur", "workstation", "desktop", "notebook"],
        "aliases": ["marque carte graphique", "graphics adapter brand", "gpu brand", "graphics card brand", "fabricant carte graphique"],
    },
    {
        "key": "os",
        "label_fr": "Système d'exploitation",
        "type": "enum",
        "unit": None,
        "categories": ["ordinateur", "laptop", "portable", "workstation", "desktop", "notebook"],
        "aliases": ["système d'exploitation", "operating system", "os", "système d exploitation", "système exploitation"],
    },
    {
        "key": "form_factor",
        "label_fr": "Facteur de forme",
        "type": "enum",
        "unit": None,
        "categories": ["ordinateur", "serveur", "workstation", "desktop"],
        "aliases": ["type de châssis", "form factor", "facteur de forme", "chassis type", "format", "type boîtier"],
    },
]


def upgrade() -> None:
    import json
    import uuid
    from datetime import datetime, timezone

    op.create_table(
        "spec_definitions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(50), nullable=False),
        sa.Column("label_fr", sa.String(200), nullable=False),
        sa.Column("type", sa.String(10), nullable=False),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("categories", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("aliases", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_spec_definitions_key"),
    )
    op.create_index("ix_spec_definitions_key", "spec_definitions", ["key"])
    op.create_index("ix_spec_definitions_is_active", "spec_definitions", ["is_active"])

    # Seed from YAML catalog
    spec_def_table = sa.table(
        "spec_definitions",
        sa.column("id", sa.UUID()),
        sa.column("key", sa.String()),
        sa.column("label_fr", sa.String()),
        sa.column("type", sa.String()),
        sa.column("unit", sa.String()),
        sa.column("categories", sa.JSON()),
        sa.column("aliases", sa.JSON()),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    now = datetime.now(timezone.utc)
    rows = [
        {
            "id": str(uuid.uuid4()),
            "key": s["key"],
            "label_fr": s["label_fr"],
            "type": s["type"],
            "unit": s.get("unit"),
            "categories": s["categories"],
            "aliases": s["aliases"],
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        for s in _SEED_SPECS
    ]
    op.bulk_insert(spec_def_table, rows)


def downgrade() -> None:
    op.drop_index("ix_spec_definitions_is_active", table_name="spec_definitions")
    op.drop_index("ix_spec_definitions_key", table_name="spec_definitions")
    op.drop_table("spec_definitions")
