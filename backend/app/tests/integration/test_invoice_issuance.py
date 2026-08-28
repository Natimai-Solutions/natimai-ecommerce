"""Integration tests for invoice issuance (M3) and order numbering (M5).

These exercise the real SQL the unit tests cannot: the gap-free counter with
its FOR UPDATE lock, the one-invoice-per-order unique constraint, and the
order-number sequence.
"""

import uuid
from decimal import Decimal

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.features.invoice.models.invoice import Invoice, InvoiceCounter
from app.features.invoice.services.invoice_service import issue_invoice_for_order
from app.features.invoice.services.numbering import allocate_invoice_number
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine
from app.features.order.models.order_status import OrderStatus
from app.features.order.services.order_number import allocate_order_number
from app.features.product.models.product import Product
from app.features.product.models.tax_rate import TaxRate
from app.features.user.models.user import User


async def _seed_paid_order(
    session: AsyncSession,
    *,
    unit_price: Decimal = Decimal("232000"),
    quantity: int = 2,
    shipping_fee: Decimal = Decimal("8700"),
    tax_rate_pct: Decimal = Decimal("16.00"),
) -> Order:
    """Create a user, a taxed product and a consistent paid order."""
    user = User(
        email=f"buyer+{uuid.uuid4().hex[:8]}@test.local",
        full_name="Jean Client",
        is_active=True,
        hashed_password="x",
    )
    status = OrderStatus(name=f"Paid-{uuid.uuid4().hex[:6]}")
    tax_rate = TaxRate(
        code=f"TGC_{uuid.uuid4().hex[:6]}",
        label="TGC normal",
        rate_pct=tax_rate_pct,
        territory_code="PF",
        valid_from="2020-01-01",
    )
    # Les frais (port, paiement) sont taxés sous le code configuré, pas sous
    # celui du produit. Sans cette ligne ils tombaient à 0 %, ce qui ajoutait un
    # second groupe au tax_breakdown — trié avant celui à 16 % — et faisait
    # échouer l'assertion positionnelle plus bas.
    fees_tax_rate = TaxRate(
        code=settings.INVOICE_FEES_TAX_CODE,
        label="TGC normal (frais)",
        rate_pct=tax_rate_pct,
        territory_code="PF",
        valid_from="2020-01-01",
    )
    session.add_all([user, status, tax_rate, fees_tax_rate])
    await session.flush()

    product = Product(
        name="Carte graphique RTX PRO",
        description="",
        base_price=unit_price,
        cost_amount=Decimal("100000"),
        cost_currency="XPF",
    )
    session.add(product)
    await session.flush()

    subtotal = unit_price * quantity
    order = Order(
        user_id=user.id,
        order_status_id=status.id,
        order_number=await allocate_order_number(session),
        currency="XPF",
        subtotal_amount=subtotal,
        shipping_fee_amount=shipping_fee,
        payment_fee_amount=Decimal("0"),
        total_fees_amount=shipping_fee,
        total_amount=subtotal + shipping_fee,
        shipping_address="12 rue des Cocotiers, 98713 Papeete",
    )
    session.add(order)
    await session.flush()

    session.add(
        OrderLine(
            order_id=order.id,
            product_id=product.id,
            quantity=quantity,
            unit_price=unit_price,
            discount_amount=Decimal("0"),
            tax_rate_id=tax_rate.id,
        )
    )
    await session.flush()
    return order


@pytest.mark.asyncio
async def test_order_number_sequence_allocates_distinct_values(
    db_session: AsyncSession,
) -> None:
    numbers = [await allocate_order_number(db_session) for _ in range(3)]

    assert len(set(numbers)) == 3
    assert all(number.startswith("CMD-") for number in numbers)
    # Strictly increasing counters.
    counters = [int(number.rsplit("-", 1)[1]) for number in numbers]
    assert counters == sorted(counters)
    assert counters[1] == counters[0] + 1


@pytest.mark.asyncio
async def test_invoice_numbering_is_continuous_per_year(
    db_session: AsyncSession,
) -> None:
    """A legal sequence has no holes: 1, 2, 3… and restarts per fiscal year."""
    first, seq_1 = await allocate_invoice_number(db_session, fiscal_year=2026)
    second, seq_2 = await allocate_invoice_number(db_session, fiscal_year=2026)
    other_year, seq_other = await allocate_invoice_number(db_session, fiscal_year=2027)

    assert (first, seq_1) == ("FAC-2026-00001", 1)
    assert (second, seq_2) == ("FAC-2026-00002", 2)
    assert (other_year, seq_other) == ("FAC-2027-00001", 1)

    counter = await db_session.get(InvoiceCounter, 2026)
    assert counter is not None
    assert counter.last_value == 2


@pytest.mark.asyncio
async def test_issue_invoice_persists_a_balanced_document(
    db_session: AsyncSession,
) -> None:
    order = await _seed_paid_order(db_session)

    invoice = await issue_invoice_for_order(db_session, order_id=order.id, commit=False)
    await db_session.flush()

    assert invoice.invoice_number.startswith("FAC-")
    assert invoice.order_id == order.id
    assert invoice.total_incl_tax == order.total_amount
    assert invoice.total_excl_tax + invoice.total_tax == invoice.total_incl_tax

    # The snapshot carries what the PDF prints.
    snapshot = invoice.snapshot
    assert snapshot["order"]["number"] == order.order_number
    assert snapshot["buyer"]["name"] == "Jean Client"
    assert len(snapshot["lines"]) == 1
    assert snapshot["lines"][0]["description"] == "Carte graphique RTX PRO"

    # Recherché par taux et non par position : tax_breakdown est trié par taux
    # croissant, donc un indice figé se déplace dès qu'un groupe s'ajoute.
    rates = {entry["rate_pct"]: entry for entry in snapshot["tax_breakdown"]}
    assert set(rates) == {"16.00"}, snapshot["tax_breakdown"]
    taxed = rates["16.00"]
    assert Decimal(taxed["base_excl_tax"]) + Decimal(taxed["tax_amount"]) == Decimal(
        taxed["total_incl_tax"]
    )


@pytest.mark.asyncio
async def test_issue_invoice_twice_returns_the_same_document(
    db_session: AsyncSession,
) -> None:
    """Replaying payment.captured must not issue a second invoice."""
    order = await _seed_paid_order(db_session)

    first = await issue_invoice_for_order(db_session, order_id=order.id, commit=False)
    await db_session.flush()
    second = await issue_invoice_for_order(db_session, order_id=order.id, commit=False)
    await db_session.flush()

    assert first.id == second.id
    assert first.invoice_number == second.invoice_number

    result = await db_session.exec(select(Invoice).where(Invoice.order_id == order.id))
    assert len(result.all()) == 1
