"""datetimes stockés en UTC avec fuseau (timestamptz)

Revision ID: f4a8c2e6d9b1
Revises: o6f3b9d2e8a4
Create Date: 2026-09-30 03:00:00.000000

sqlmodel 0.0.45 mappe désormais `datetime` sur `UTCDateTime`, un
`DateTime(timezone=True)` qui exige des valeurs conscientes du fuseau à
l'écriture et renvoie des valeurs UTC conscientes à la lecture. Les colonnes
créées jusqu'ici en `sa.DateTime()` sont des `timestamp without time zone`
qui contenaient de l'UTC naïf (conteneurs en UTC, `datetime.now()` côté
application). On les convertit en `timestamptz` en déclarant explicitement
que les valeurs existantes sont de l'UTC (`AT TIME ZONE 'UTC'`), plutôt que
de laisser Postgres les interpréter selon le fuseau de la session.

Liste générée depuis SQLModel.metadata (colonnes de type UTCDateTime), moins
les treize colonnes déjà créées en `timestamptz` par des migrations
antérieures (départs groupés, spec_definitions, supplier_orders,
system_settings, orders.cgv_accepted_at) : rien à convertir pour elles, et le
downgrade ne doit pas les rendre naïves.

"""

import sqlalchemy as sa
from alembic import op

revision = "f4a8c2e6d9b1"
down_revision = "o6f3b9d2e8a4"
branch_labels = None
depends_on = None

# (table, colonne) — 154 colonnes sur 61 tables.
DATETIME_COLUMNS: tuple[tuple[str, str], ...] = (
    ("addresses", "created_at"),
    ("addresses", "modify_at"),
    ("analytic_products", "created_at"),
    ("analytic_products", "modify_at"),
    ("analytics_sales", "created_at"),
    ("analytics_sales", "modify_at"),
    ("analytics_users", "created_at"),
    ("analytics_users", "modify_at"),
    ("brands", "created_at"),
    ("brands", "modify_at"),
    ("carriers", "created_at"),
    ("carriers", "modify_at"),
    ("cart_items", "created_at"),
    ("cart_items", "modify_at"),
    ("carts", "abandonment_reminded_at"),
    ("carts", "created_at"),
    ("carts", "last_activity_at"),
    ("carts", "modify_at"),
    ("categories", "created_at"),
    ("categories", "modify_at"),
    ("content_pages", "created_at"),
    ("content_pages", "modify_at"),
    ("credit_notes", "emailed_at"),
    ("credit_notes", "issued_at"),
    ("currency_rates", "created_at"),
    ("currency_rates", "modify_at"),
    ("delivery_tasks", "created_at"),
    ("delivery_tasks", "delivered_at"),
    ("delivery_tasks", "modify_at"),
    ("delivery_tasks", "scheduled_at"),
    ("departure_receipt_lines", "created_at"),
    ("departure_receipt_lines", "modify_at"),
    ("departure_reminders", "created_at"),
    ("departure_reminders", "modify_at"),
    ("discounts", "created_at"),
    ("discounts", "end_date"),
    ("discounts", "modify_at"),
    ("discounts", "start_date"),
    ("group_security", "created_at"),
    ("group_security", "modify_at"),
    ("group_upgrade_requests", "created_at"),
    ("group_upgrade_requests", "reviewed_at"),
    ("grouped_departures", "created_at"),
    ("grouped_departures", "modify_at"),
    ("groups", "created_at"),
    ("groups", "modify_at"),
    ("inventories", "created_at"),
    ("inventories", "modify_at"),
    ("inventory_stock_movements", "created_at"),
    ("inventory_stock_movements", "modify_at"),
    ("inventory_stock_movements", "processed_at"),
    ("invoices", "emailed_at"),
    ("invoices", "issued_at"),
    ("notifications", "created_at"),
    ("notifications", "modify_at"),
    ("order_lines", "created_at"),
    ("order_lines", "modify_at"),
    ("order_statuses", "created_at"),
    ("order_statuses", "modify_at"),
    ("orders", "balance_paid_at"),
    ("orders", "balance_requested_at"),
    ("orders", "created_at"),
    ("orders", "modify_at"),
    ("outbox_event", "created_at"),
    ("outbox_event", "next_run_at"),
    ("outbox_event", "updated_at"),
    ("partners", "created_at"),
    ("partners", "modify_at"),
    ("payment_attachments", "created_at"),
    ("payment_attachments", "modify_at"),
    ("payment_logs", "created_at"),
    ("payment_logs", "modify_at"),
    ("payment_methods", "created_at"),
    ("payment_methods", "modify_at"),
    ("payment_status", "created_at"),
    ("payment_status", "modify_at"),
    ("payment_validations", "created_at"),
    ("payment_validations", "modify_at"),
    ("payments", "created_at"),
    ("payments", "modify_at"),
    ("places", "created_at"),
    ("places", "modify_at"),
    ("price_groups", "created_at"),
    ("price_groups", "modify_at"),
    ("product_price_history", "created_at"),
    ("products", "created_at"),
    ("products", "featured_until"),
    ("products", "last_enrichment_sync"),
    ("products", "last_supplier_sync"),
    ("products", "modify_at"),
    ("products", "sale_price_cached_at"),
    ("products", "supplier_missing_since"),
    ("quote_requests", "created_at"),
    ("quote_requests", "handled_at"),
    ("quote_requests", "modify_at"),
    ("quote_requests", "quoted_at"),
    ("refunds", "created_at"),
    ("refunds", "modify_at"),
    ("refunds", "processed_at"),
    ("reviews", "created_at"),
    ("reviews", "modify_at"),
    ("shipping_route_tracking_consolidations", "created_at"),
    ("shipping_route_tracking_consolidations", "modify_at"),
    ("shipping_route_tracking_logs", "created_at"),
    ("shipping_route_tracking_logs", "modify_at"),
    ("shipping_route_trackings", "created_at"),
    ("shipping_route_trackings", "estimated_delivery"),
    ("shipping_route_trackings", "last_status_update"),
    ("shipping_route_trackings", "modify_at"),
    ("shipping_route_trackings", "selected_at"),
    ("shipping_routes", "created_at"),
    ("shipping_routes", "modify_at"),
    ("status_definitions", "created_at"),
    ("status_definitions", "modify_at"),
    ("status_transitions", "created_at"),
    ("status_transitions", "modify_at"),
    ("stock_alerts", "created_at"),
    ("stock_alerts", "modify_at"),
    ("stock_alerts", "notified_at"),
    ("store_credit_entries", "created_at"),
    ("store_credit_entries", "modify_at"),
    ("supplier_product_mappings", "created_at"),
    ("supplier_product_mappings", "last_synced"),
    ("supplier_product_mappings", "updated_at"),
    ("supplier_sync_logs", "completed_at"),
    ("supplier_sync_logs", "created_at"),
    ("supplier_sync_logs", "started_at"),
    ("supplier_sync_logs", "updated_at"),
    ("suppliers", "created_at"),
    ("suppliers", "updated_at"),
    ("tax_rates", "created_at"),
    ("tax_rates", "modify_at"),
    ("user_groups", "joined_at"),
    ("user_notifications", "created_at"),
    ("user_notifications", "modify_at"),
    ("user_notifications", "read_at"),
    ("user_notifications", "sent_at"),
    ("user_oauth_links", "created_at"),
    ("user_refresh_tokens", "created_at"),
    ("user_refresh_tokens", "expires_at"),
    ("user_refresh_tokens", "last_used_at"),
    ("user_refresh_tokens", "modify_at"),
    ("user_refresh_tokens", "revoked_at"),
    ("users", "created_at"),
    ("users", "email_verification_token_expires"),
    ("users", "last_login"),
    ("users", "last_verification_email_sent"),
    ("users", "locked_until"),
    ("users", "modify_at"),
    ("users", "password_reset_token_expires"),
    ("wishlist_items", "created_at"),
    ("wishlist_items", "modify_at"),
    ("wishlists", "created_at"),
    ("wishlists", "modify_at"),
)


def upgrade() -> None:
    for table, column in DATETIME_COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(timezone=True),
            existing_type=sa.DateTime(),
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )


def downgrade() -> None:
    for table, column in DATETIME_COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(),
            existing_type=sa.DateTime(timezone=True),
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )
