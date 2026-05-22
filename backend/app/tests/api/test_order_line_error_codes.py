from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.routes import order_line as order_line_routes
from app.core.errors import AppError


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_get_product_order_lines_returns_order_admin_required_for_non_admin() -> (
    None
):
    session = AsyncMock()
    product_id = uuid4()
    current_user = SimpleNamespace(id=uuid4(), is_superuser=False)

    with pytest.raises(AppError) as exc_info:
        await order_line_routes.get_product_order_lines(
            session=session,
            current_user=current_user,
            product_id=product_id,
        )

    assert exc_info.value.code == "order.admin_required"
    assert exc_info.value.status_code == 403
    assert exc_info.value.details == {"resource": "order_line.product"}
