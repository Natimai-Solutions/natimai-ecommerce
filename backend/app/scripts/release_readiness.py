"""Rapport de préparation à l'ouverture (PP-F).

Le plan liste quatre vérifications « à tracer faites avant ouverture ». Une
consigne dont personne ne connaît la valeur du jour n'est pas une vérification :
ce script les mesure, et sort en code non nul quand un seuil est franchi.

    docker compose exec -T api python -m app.scripts.release_readiness

Il ne modifie rien. Chaque contrôle explique ce qu'il mesure et pourquoi le
seuil est là, parce que le chiffre seul ne dit pas quoi en faire.
"""

from __future__ import annotations

import asyncio
import datetime
import sys
from dataclasses import dataclass

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import engine
from app.features.payment.models.payment_attachment import PaymentAttachment
from app.features.product.models.currency_rate import CurrencyRate
from app.features.product.models.product import Product

#: Sous ce taux, le filtre `is_enriched` de la vitrine vide le catalogue : le
#: plan prévoit alors soit d'élargir Icecat, soit d'afficher sans specs.
MIN_ENRICHMENT_PCT = 80.0
#: Un taux de change saisi à la main et oublié fausse tous les prix de vente.
MAX_FX_AGE_DAYS = 30


@dataclass
class Check:
    """Un contrôle et son verdict."""

    name: str
    value: str
    ok: bool
    hint: str


async def _check_enrichment(session: AsyncSession) -> Check:
    """Part du catalogue réellement visible en vitrine.

    La recherche publique filtre sur ``is_enriched`` : un produit non enrichi
    est invisible, quel que soit son stock.
    """
    total = (
        await session.exec(
            select(func.count())
            .select_from(Product)
            .where(col(Product.is_active).is_(True))
        )
    ).one()
    if not total:
        return Check(
            "Enrichissement Icecat",
            "aucun produit actif",
            False,
            "Le catalogue est vide : lancer une synchronisation fournisseur.",
        )

    enriched = (
        await session.exec(
            select(func.count())
            .select_from(Product)
            .where(
                col(Product.is_active).is_(True),
                col(Product.is_enriched).is_(True),
            )
        )
    ).one()
    pct = 100.0 * enriched / total
    return Check(
        "Enrichissement Icecat",
        f"{enriched}/{total} produits actifs ({pct:.1f} %)",
        pct >= MIN_ENRICHMENT_PCT,
        (
            f"Sous {MIN_ENRICHMENT_PCT:.0f} %, la vitrine est presque vide : "
            "élargir Icecat (offre Full) ou prévoir un affichage sans specs."
        ),
    )


async def _check_categories(session: AsyncSession) -> Check:
    """Produits sans catégorie : ni filtrables, ni rattachés à un taux de taxe
    par défaut."""
    missing = (
        await session.exec(
            select(func.count())
            .select_from(Product)
            .where(
                col(Product.is_active).is_(True),
                col(Product.category_id).is_(None),
            )
        )
    ).one()
    return Check(
        "Rattachement des catégories",
        f"{missing} produit(s) actif(s) sans category_id",
        missing == 0,
        (
            "Sans catégorie, le produit échappe aux filtres et ne bénéficie "
            "d'aucun taux de taxe par défaut : faire le backfill."
        ),
    )


async def _check_fx_rates(session: AsyncSession) -> Check:
    """Fraîcheur des taux de change saisis à la main.

    Le coût fournisseur est converti avec ces taux : un taux figé depuis des
    mois se répercute sur chaque prix affiché.
    """
    rows = (
        await session.exec(
            select(CurrencyRate.currency_code, func.max(CurrencyRate.valid_from))
            .where(col(CurrencyRate.is_active).is_(True))
            .group_by(col(CurrencyRate.currency_code))
        )
    ).all()
    if not rows:
        return Check(
            "Fraîcheur des taux de change",
            "aucun taux actif",
            False,
            "Aucune conversion possible : créer au moins le taux de la devise "
            "des coûts fournisseurs.",
        )

    today = datetime.date.today()
    stale = [
        (code, (today - valid_from).days)
        for code, valid_from in rows
        if (today - valid_from).days > MAX_FX_AGE_DAYS
    ]
    detail = ", ".join(f"{code} ({days} j)" for code, days in stale) or "tous récents"
    return Check(
        "Fraîcheur des taux de change",
        f"{len(rows)} devise(s) — {detail}",
        not stale,
        (
            f"Un taux de plus de {MAX_FX_AGE_DAYS} jours fausse les prix de "
            "vente : le rafraîchir depuis l'écran admin."
        ),
    )


async def _check_storage(session: AsyncSession) -> Check:
    """Volumétrie des pièces jointes — informatif, pas bloquant."""
    count = (
        await session.exec(select(func.count()).select_from(PaymentAttachment))
    ).one()
    total_bytes = (
        await session.exec(select(func.coalesce(func.sum(PaymentAttachment.size), 0)))
    ).one()
    megabytes = (total_bytes or 0) / (1024 * 1024)
    return Check(
        "Volumétrie des pièces jointes",
        f"{count} fichier(s), {megabytes:.1f} Mo",
        True,
        "Informatif : à comparer à l'espace du volume de stockage.",
    )


async def main() -> None:
    """Exécuter tous les contrôles et rendre un code de sortie."""
    async with AsyncSession(engine) as session:
        checks = [
            await _check_enrichment(session),
            await _check_categories(session),
            await _check_fx_rates(session),
            await _check_storage(session),
        ]

    print("Préparation à l'ouverture\n")
    for check in checks:
        marker = "OK  " if check.ok else "!!  "
        print(f"{marker}{check.name} : {check.value}")
        if not check.ok:
            print(f"      → {check.hint}")

    failed = [check for check in checks if not check.ok]
    print()
    if failed:
        print(f"{len(failed)} contrôle(s) à traiter avant ouverture.", file=sys.stderr)
        raise SystemExit(1)
    print("Tous les contrôles passent.")


if __name__ == "__main__":
    asyncio.run(main())
