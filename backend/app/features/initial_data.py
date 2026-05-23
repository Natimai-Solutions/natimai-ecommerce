from datetime import date
from decimal import Decimal

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.payment.crud.payment_method import crud_payment_method
from app.features.payment.crud.payment_status import crud_payment_status
from app.features.payment.models.payment_method import (
    PaymentMethod,
    PaymentMethodCreate,
)
from app.features.payment.models.payment_status import PaymentStatusCreate
from app.features.payment.providers.document_validated import (
    DOCUMENT_STATUS_DOCUMENT_REQUIRED,
    DOCUMENT_STATUS_DOCUMENT_UPLOADED,
    DOCUMENT_STATUS_UNDER_REVIEW,
)
from app.features.payment.providers.manual import (
    MANUAL_STATUS_AWAITING_VALIDATION,
    MANUAL_STATUS_COMPLETED,
    MANUAL_STATUS_FAILED,
)
from app.features.product.models.currency_rate import CurrencyRate, CurrencyRateSource
from app.features.product.models.price_group import PriceGroup
from app.features.product.models.tax_rate import TaxRate

DEFAULT_PAYMENT_STATUSES: tuple[tuple[str, str], ...] = (
    ("Pending", "Payment initiated, awaiting provider action"),
    (MANUAL_STATUS_AWAITING_VALIDATION, "Awaiting manual admin validation"),
    (DOCUMENT_STATUS_DOCUMENT_REQUIRED, "Waiting for document upload from client"),
    (DOCUMENT_STATUS_DOCUMENT_UPLOADED, "Document uploaded, awaiting AV scan"),
    (DOCUMENT_STATUS_UNDER_REVIEW, "Document under admin review"),
    (MANUAL_STATUS_COMPLETED, "Payment confirmed and captured"),
    (MANUAL_STATUS_FAILED, "Payment failed or was rejected"),
)


async def _seed_payment_statuses(session: AsyncSession) -> None:
    """Execute seed payment statuses."""
    for name, description in DEFAULT_PAYMENT_STATUSES:
        existing = await crud_payment_status.get_by_name(session, name=name)
        if existing is not None:
            continue
        await crud_payment_status.create_draft(
            session=session,
            data=PaymentStatusCreate(name=name, description=description),
            user=None,
        )


async def _seed_manual_payment_methods(session: AsyncSession) -> None:
    """Execute seed manual payment methods."""
    methods = (
        {
            "name": "Chèque",
            "description": "Paiement par chèque, validé manuellement à réception.",
            "provider_code": "manual_check",
            "sort_order": 80,
            "requires_admin_validation": True,
            "requires_document_upload": False,
        },
        {
            "name": "Virement bancaire",
            "description": "Paiement par virement bancaire, validé manuellement à réception.",
            "provider_code": "manual_transfer",
            "sort_order": 90,
            "requires_admin_validation": True,
            "requires_document_upload": False,
        },
        {
            "name": "Bon de commande",
            "description": (
                "Paiement sur bon de commande signé. Le client téléverse "
                "son BC et notre équipe valide la commande après vérification."
            ),
            "provider_code": "po_public",
            "sort_order": 100,
            "requires_admin_validation": True,
            "requires_document_upload": True,
        },
    )

    for spec in methods:
        statement = select(PaymentMethod).where(
            PaymentMethod.provider_code == spec["provider_code"]
        )
        result = await session.exec(statement)
        if result.first() is not None:
            continue

        await crud_payment_method.create_draft(
            session=session,
            data=PaymentMethodCreate(
                name=spec["name"],
                description=spec["description"],
                provider_code=spec["provider_code"],
                requires_admin_validation=spec["requires_admin_validation"],
                requires_document_upload=spec["requires_document_upload"],
                sort_order=spec["sort_order"],
                fee=Decimal("0.00"),
            ),
            user=None,
        )


async def _seed_price_groups(session: AsyncSession) -> None:
    """Seed default price groups used by runtime pricing."""
    groups = (
        {
            "code": "PARTICULIER",
            "label": "Particulier",
            "margin_rate_pct": Decimal("30.00"),
            "default": True,
            "requires_validation": False,
        },
        {
            "code": "PROFESSIONNEL",
            "label": "Professionnel",
            "margin_rate_pct": Decimal("25.00"),
            "default": False,
            "requires_validation": True,
        },
        {
            "code": "REVENDEUR",
            "label": "Revendeur",
            "margin_rate_pct": Decimal("12.00"),
            "default": False,
            "requires_validation": True,
        },
        {
            "code": "PUBLIC",
            "label": "Public / Etablissements",
            "margin_rate_pct": Decimal("18.00"),
            "default": False,
            "requires_validation": True,
        },
    )

    for group in groups:
        statement = select(PriceGroup).where(PriceGroup.code == group["code"])
        result = await session.exec(statement)
        existing = result.first()
        if existing is not None:
            continue
        session.add(PriceGroup.model_validate(group))


async def _seed_tax_rates(session: AsyncSession) -> None:
    """Seed baseline PF tax rates used by pricing resolution."""
    rates = (
        {
            "code": "TGC_NORMAL",
            "label": "TGC normal",
            "rate_pct": Decimal("16.00"),
            "territory_code": "PF",
            "valid_from": date.today(),
            "valid_until": None,
        },
        {
            "code": "TGC_REDUIT",
            "label": "TGC reduit",
            "rate_pct": Decimal("5.00"),
            "territory_code": "PF",
            "valid_from": date.today(),
            "valid_until": None,
        },
        {
            "code": "TGC_EXONERE",
            "label": "TGC exonere",
            "rate_pct": Decimal("0.00"),
            "territory_code": "PF",
            "valid_from": date.today(),
            "valid_until": None,
        },
    )

    for rate in rates:
        statement = select(TaxRate).where(
            TaxRate.code == rate["code"],
            TaxRate.territory_code == rate["territory_code"],
        )
        result = await session.exec(statement)
        if result.first() is not None:
            continue
        session.add(TaxRate.model_validate(rate))


async def _seed_currency_rates(session: AsyncSession) -> None:
    """Seed baseline FX rates used by pricing conversion (cost → XPF)."""
    rates = (
        {
            "currency_code": "EUR",
            "rate_to_xpf": Decimal("119.332"),
        },
        {
            "currency_code": "USD",
            "rate_to_xpf": Decimal("100.000"),
        },
    )

    for rate in rates:
        statement = select(CurrencyRate).where(
            CurrencyRate.currency_code == rate["currency_code"],
            CurrencyRate.is_active == True,  # noqa: E712
            CurrencyRate.valid_until == None,  # noqa: E711
        )
        result = await session.exec(statement)
        if result.first() is not None:
            continue
        session.add(
            CurrencyRate(
                currency_code=rate["currency_code"],
                rate_to_xpf=rate["rate_to_xpf"],
                valid_from=date.today(),
                valid_until=None,
                source=CurrencyRateSource.manual,
                is_active=True,
                is_admin_active=True,
            )
        )


async def initial_data(session: AsyncSession) -> None:
    """Execute initial data."""
    await _seed_payment_statuses(session)
    await _seed_manual_payment_methods(session)
    await _seed_price_groups(session)
    await _seed_tax_rates(session)
    await _seed_currency_rates(session)
