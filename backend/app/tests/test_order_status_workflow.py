"""Tests pour le workflow des statuts de commande."""

import pytest
import uuid
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.order.constants import OrderStatusCode
from app.features.order.crud.order_crud import crud_order
from app.features.order.crud.order_status_crud import crud_order_status
from app.features.order.models.order import OrderCreate
from app.features.order.models.order_status import OrderStatusCreate
from app.features.user.models.user import User
from app.features.base.crud import CrudOperationError


@pytest.mark.asyncio
async def test_order_status_creation(db: AsyncSession):
    """Test de création d'un statut avec tous les nouveaux champs."""
    status_data = OrderStatusCreate(
        name="Test Status",
        code="TEST_STATUS",
        sequence=100,
        is_final=False,
        is_error=False,
        is_cancellation=False,
        color="#FF5733",
        description="Test status description",
    )
    
    status = await crud_order_status.create(db, data=status_data, user=None)
    
    assert status.id is not None
    assert status.code == "TEST_STATUS"
    assert status.sequence == 100
    assert status.is_final is False
    assert status.color == "#FF5733"


@pytest.mark.asyncio
async def test_order_status_get_by_code(db: AsyncSession):
    """Test de récupération d'un statut par son code."""
    status_data = OrderStatusCreate(
        name="Test Status Code",
        code="TEST_CODE",
        sequence=10,
    )
    
    created_status = await crud_order_status.create(db, data=status_data, user=None)
    found_status = await crud_order_status.get_by_code(db, code="TEST_CODE")
    
    assert found_status is not None
    assert found_status.id == created_status.id
    assert found_status.code == "TEST_CODE"


@pytest.mark.asyncio
async def test_order_status_get_ordered(db: AsyncSession):
    """Test de récupération des statuts ordonnés par sequence."""
    statuses_data = [
        OrderStatusCreate(name="Status 3", code="CODE_3", sequence=30),
        OrderStatusCreate(name="Status 1", code="CODE_1", sequence=10),
        OrderStatusCreate(name="Status 2", code="CODE_2", sequence=20),
    ]
    
    for status_data in statuses_data:
        await crud_order_status.create(db, data=status_data, user=None)
    
    ordered_statuses = await crud_order_status.get_ordered(db)
    
    assert len(ordered_statuses) >= 3
    # Vérifier que les statuts sont ordonnés par sequence
    sequences = [s.sequence for s in ordered_statuses if s.code.startswith("CODE_")]
    assert sequences == [10, 20, 30]


@pytest.mark.asyncio
async def test_change_order_status_success(
    db: AsyncSession, 
    superuser: User
):
    """Test de changement de statut d'une commande."""
    # Créer deux statuts
    status_pending = await crud_order_status.create(
        db,
        data=OrderStatusCreate(
            name="Pending",
            code=OrderStatusCode.PENDING,
            sequence=0,
            is_final=False,
        ),
        user=None,
    )
    
    status_confirmed = await crud_order_status.create(
        db,
        data=OrderStatusCreate(
            name="Confirmed",
            code=OrderStatusCode.PAYMENT_CONFIRMED,
            sequence=10,
            is_final=False,
        ),
        user=None,
    )
    
    # Créer une commande
    order_data = OrderCreate(
        user_id=superuser.id,
        order_status_id=status_pending.id,
        total_amount=100.00,
    )
    order = await crud_order.create(db, data=order_data, user=superuser)
    
    # Changer le statut
    updated_order = await crud_order.change_status(
        db,
        order_id=order.id,
        new_status_id=status_confirmed.id,
        user=superuser,
    )
    
    assert updated_order.order_status_id == status_confirmed.id
    assert updated_order.modify_by_id == superuser.id


@pytest.mark.asyncio
async def test_change_status_from_final_status_fails(
    db: AsyncSession,
    superuser: User
):
    """Test qu'on ne peut pas changer un statut final."""
    # Créer un statut final
    status_delivered = await crud_order_status.create(
        db,
        data=OrderStatusCreate(
            name="Delivered",
            code=OrderStatusCode.DELIVERED,
            sequence=40,
            is_final=True,
        ),
        user=None,
    )
    
    status_other = await crud_order_status.create(
        db,
        data=OrderStatusCreate(
            name="Other",
            code="OTHER",
            sequence=50,
            is_final=False,
        ),
        user=None,
    )
    
    # Créer une commande avec statut final
    order_data = OrderCreate(
        user_id=superuser.id,
        order_status_id=status_delivered.id,
        total_amount=100.00,
    )
    order = await crud_order.create(db, data=order_data, user=superuser)
    
    # Tenter de changer le statut depuis un statut final
    with pytest.raises(CrudOperationError) as exc_info:
        await crud_order.change_status(
            db,
            order_id=order.id,
            new_status_id=status_other.id,
            user=superuser,
        )
    
    assert "Cannot change status from final state" in str(exc_info.value)


@pytest.mark.asyncio
async def test_change_status_invalid_status_fails(
    db: AsyncSession,
    superuser: User
):
    """Test qu'on ne peut pas changer vers un statut inexistant."""
    status_pending = await crud_order_status.create(
        db,
        data=OrderStatusCreate(
            name="Pending",
            code=OrderStatusCode.PENDING,
            sequence=0,
        ),
        user=None,
    )
    
    order_data = OrderCreate(
        user_id=superuser.id,
        order_status_id=status_pending.id,
        total_amount=100.00,
    )
    order = await crud_order.create(db, data=order_data, user=superuser)
    
    fake_status_id = uuid.uuid4()
    
    with pytest.raises(CrudOperationError) as exc_info:
        await crud_order.change_status(
            db,
            order_id=order.id,
            new_status_id=fake_status_id,
            user=superuser,
        )
    
    assert "not found" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_order_status_code_unique_constraint(db: AsyncSession):
    """Test que le code de statut doit être unique."""
    status_data = OrderStatusCreate(
        name="Status 1",
        code="UNIQUE_CODE",
        sequence=0,
    )
    
    await crud_order_status.create(db, data=status_data, user=None)
    
    # Tenter de créer un autre statut avec le même code
    duplicate_data = OrderStatusCreate(
        name="Status 2",
        code="UNIQUE_CODE",
        sequence=10,
    )
    
    with pytest.raises(Exception):  # SQLAlchemy IntegrityError
        await crud_order_status.create(db, data=duplicate_data, user=None)
