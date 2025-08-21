from __future__ import annotations

import uuid
from typing import Any, Optional, Protocol, runtime_checkable

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.registry import CrudRegistry

# Optional: import concrete schemas if available
try:
    from app.api.order.models.order import OrderUpdate  # type: ignore
except Exception:  # pragma: no cover
    OrderUpdate = None  # type: ignore

try:
    from app.api.user.models.notification import (  # type: ignore
        NotificationCreate,
        NotificationType,
    )
except Exception:  # pragma: no cover
    NotificationCreate = None  # type: ignore
    NotificationType = None  # type: ignore


@runtime_checkable
class OrderCrudLike(Protocol):
    async def update(self, session: AsyncSession, *, id: uuid.UUID, data: Any, user: Any | None = None) -> Any:
        ...
    async def update_draft(self, session: AsyncSession, *, id: uuid.UUID, data: Any, user: Any | None = None) -> Any:
        ...


@runtime_checkable
class NotificationCrudLike(Protocol):
    async def create(self, session: AsyncSession, *, data: Any, user: Any | None = None) -> Any:
        ...
    async def create_draft(self, session: AsyncSession, *, data: Any, user: Any | None = None) -> Any:
        ...


class OrderService:
    """Application service for order-related use-cases.

    Orchestrates multiple CRUDs and integrations (email, notifications),
    keeping side-effects out of CRUDs and routes.
    """

    def __init__(self, env: CrudRegistry):
        self.env = env

    def _get_crud(self, primary: str, fallback: str) -> Any:
        """Fetch a CRUD from the registry by alias or original name."""
        inst = self.env.get(primary)
        if inst is not None:
            return inst
        inst = self.env.get(fallback)
        if inst is not None:
            return inst
        raise KeyError(f"CRUD not found in registry: {primary} | {fallback}")

    async def validate_order(
    self,
    session: AsyncSession,
    *,
    order_id: uuid.UUID,
    notifying_user_id: Optional[uuid.UUID] = None,
    crud_order: Optional[OrderCrudLike] = None,
    crud_notification: Optional[NotificationCrudLike] = None,
    email_sender: Any | None = None,
) -> Any:
        """Validate an order, then create a notification and (optionally) send an email.

        Contract:
                - Inputs: order_id, db session, optional user to notify
                - Transaction: order update and notification creation are ATOMIC
                    (if notification fails, the order update is rolled back)
                - Side-effects: email is sent after commit and does NOT affect the transaction
                - Errors: propagates errors from CRUD operations
        """
        # Resolve dependencies (allow explicit injection or registry lookup)
        crud_order = crud_order or self._get_crud("order", "crud_order")
        crud_notification = crud_notification or self._get_crud("notification", "crud_notification")
        if email_sender is None:
            email_sender = getattr(self.env, "email_sender", None)

        # 1) Build payloads
        if OrderUpdate is not None:
            update_data = OrderUpdate()  # adjust: set status field if your model has it
        else:
            update_data = {}

        notif_payload = None
        if notifying_user_id is not None:
            if NotificationCreate is not None and NotificationType is not None:
                notif_payload = NotificationCreate(
                    title="Commande validée",
                    content=f"Votre commande {order_id} a été validée.",
                    type=NotificationType.ORDER,
                    user_id=notifying_user_id,
                )
            else:
                notif_payload = {
                    "title": "Commande validée",
                    "content": f"Votre commande {order_id} a été validée.",
                    "type": "ORDER",
                    "user_id": str(notifying_user_id),
                }

        # 2) ATOMIC block: update order + create notification (draft-level, single commit)
        async with session.begin():
            order = await crud_order.update_draft(session, id=order_id, data=update_data, user=None)  # type: ignore[arg-type]
            if notif_payload is not None:
                await crud_notification.create_draft(session, data=notif_payload, user=None)  # type: ignore[arg-type]

        # After commit, refresh order state
        try:
            await session.refresh(order)
        except Exception:
            pass

    # 3) Side-effect: send email (integration optional, non-transactional)
        if email_sender is not None and hasattr(email_sender, "send_order_confirmation"):
            try:
                maybe_coro = email_sender.send_order_confirmation(order)
                if hasattr(maybe_coro, "__await__"):
                    await maybe_coro
            except Exception:
                # Swallow integration errors to not block the main flow
                pass

        return order
