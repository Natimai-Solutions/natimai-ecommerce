"""add place hierarchy, postal codes, route served zones, address place

Revision ID: a9c5e1f3b7d2
Revises: d8e3f5b2a6c4
Create Date: 2026-07-03 08:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "a9c5e1f3b7d2"
down_revision = "d8e3f5b2a6c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- places: self-referencing hierarchy (commune → île → archipel → pays)
    op.add_column("places", sa.Column("parent_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_places_parent_id"), "places", ["parent_id"], unique=False)
    op.create_foreign_key(
        "fk_places_parent_id", "places", "places", ["parent_id"], ["id"]
    )

    # --- postal code → zone mapping (address form island deduction)
    op.create_table(
        "place_postal_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("place_id", sa.Uuid(), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("postal_code", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(["place_id"], ["places.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("country", "postal_code", name="uq_place_postal_code"),
    )
    op.create_index(
        op.f("ix_place_postal_codes_place_id"),
        "place_postal_codes",
        ["place_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_place_postal_codes_country"),
        "place_postal_codes",
        ["country"],
        unique=False,
    )
    op.create_index(
        op.f("ix_place_postal_codes_postal_code"),
        "place_postal_codes",
        ["postal_code"],
        unique=False,
    )

    # --- shipping_routes: destination-independent last-leg flag
    op.add_column(
        "shipping_routes",
        sa.Column(
            "always_available",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # --- zones served by a route (n-n)
    op.create_table(
        "route_served_places",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("route_id", sa.Uuid(), nullable=False),
        sa.Column("place_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["route_id"], ["shipping_routes.id"]),
        sa.ForeignKeyConstraint(["place_id"], ["places.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("route_id", "place_id", name="uq_route_served_place"),
    )
    op.create_index(
        op.f("ix_route_served_places_route_id"),
        "route_served_places",
        ["route_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_route_served_places_place_id"),
        "route_served_places",
        ["place_id"],
        unique=False,
    )

    # --- addresses: geographic zone (auto-resolved from postal code)
    op.add_column("addresses", sa.Column("place_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_addresses_place_id"), "addresses", ["place_id"], unique=False
    )
    op.create_foreign_key(
        "fk_addresses_place_id", "addresses", "places", ["place_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_addresses_place_id", "addresses", type_="foreignkey")
    op.drop_index(op.f("ix_addresses_place_id"), table_name="addresses")
    op.drop_column("addresses", "place_id")

    op.drop_index(
        op.f("ix_route_served_places_place_id"), table_name="route_served_places"
    )
    op.drop_index(
        op.f("ix_route_served_places_route_id"), table_name="route_served_places"
    )
    op.drop_table("route_served_places")

    op.drop_column("shipping_routes", "always_available")

    op.drop_index(
        op.f("ix_place_postal_codes_postal_code"), table_name="place_postal_codes"
    )
    op.drop_index(
        op.f("ix_place_postal_codes_country"), table_name="place_postal_codes"
    )
    op.drop_index(
        op.f("ix_place_postal_codes_place_id"), table_name="place_postal_codes"
    )
    op.drop_table("place_postal_codes")

    op.drop_constraint("fk_places_parent_id", "places", type_="foreignkey")
    op.drop_index(op.f("ix_places_parent_id"), table_name="places")
    op.drop_column("places", "parent_id")
