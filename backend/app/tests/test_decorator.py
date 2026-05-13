"""Tests for the track_crud_operation decorator."""

import pytest

from app.features.base.crud import CrudOperationError, track_crud_operation


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@track_crud_operation
async def _method_no_args(
    session: object, *, data: object, user: object = None
) -> str:
    _ = (session, data, user)
    return "success"


@track_crud_operation(step_name="custom_operation")
async def _method_with_args(
    session: object, *, data: object, user: object = None
) -> str:
    _ = (session, data, user)
    return "success"


@track_crud_operation
async def _method_error(
    session: object, *, data: object, user: object = None
) -> None:
    _ = (session, data, user)
    raise ValueError("Test error")


@pytest.mark.anyio
async def test_track_crud_operation_without_args() -> None:
    result = await _method_no_args(None, data={"test": "data"}, user=None)
    assert result == "success"


@pytest.mark.anyio
async def test_track_crud_operation_with_args() -> None:
    result = await _method_with_args(None, data={"test": "data"}, user=None)
    assert result == "success"


@pytest.mark.anyio
async def test_track_crud_operation_wraps_errors() -> None:
    with pytest.raises(CrudOperationError):
        await _method_error(None, data={"test": "data"}, user=None)
