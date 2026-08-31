"""Rapport de préparation à l'ouverture (PP-F).

Le plan liste les vérifications « à tracer faites avant ouverture ». Une
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
from typing import Any

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import engine
from app.features.payment.models.payment_attachment import PaymentAttachment
from app.features.place.models import Place
from app.features.product.models.currency_rate import CurrencyRate
from app.features.product.models.product import Product
from app.features.product.services.publication import (
    customs_rate_condition,
    publication_conditions,
    weight_condition,
)

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


async def _check_publication(session: AsyncSession) -> Check:
    """Produits enrichis que la garde de publication masque encore (F1 / F5).

    Un produit dont le taux de douane ne se résout nulle part, ou qui n'a pas de
    poids, serait vendu sous son prix de revient : la vitrine le cache au lieu
    d'afficher un prix faux. Tant que ce compteur n'est pas nul, une partie du
    catalogue enrichi reste invisible — et c'est une saisie à faire, pas un bug.
    """
    base = [
        col(Product.is_active).is_(True),
        col(Product.is_admin_active).is_(True),
        col(Product.is_enriched).is_(True),
    ]

    async def _count(*extra: Any) -> int:
        return int(
            (
                await session.exec(
                    select(func.count()).select_from(Product).where(*base, *extra)
                )
            ).one()
        )

    enriched = await _count()
    if not enriched:
        return Check(
            "Publication du catalogue",
            "aucun produit enrichi",
            False,
            "Rien à publier : voir le contrôle d'enrichissement ci-dessus.",
        )

    no_customs = await _count(~customs_rate_condition())
    no_weight = await _count(~weight_condition())
    blocked = enriched - await _count(*publication_conditions())

    return Check(
        "Publication du catalogue",
        (
            f"{blocked}/{enriched} produit(s) enrichi(s) masqué(s) — "
            f"{no_customs} sans taux de douane résolu, {no_weight} sans poids"
        ),
        blocked == 0,
        (
            "Saisir le taux de douane par catégorie "
            "(PUT /admin/categories/{id}/customs-rate, taux effectif droits + "
            "TDL) et compléter les poids manquants. Détail par catégorie : "
            "GET /admin/catalog/publication-report."
        ),
    )


async def _check_import_cost_parameters(session: AsyncSession) -> Check:
    """Paramètres de coût d'import qui, laissés à zéro, ne se voient pas (F3 / F4).

    Les frais dus par déclaration et la prime d'assurance sont payés que l'on
    pense à les facturer ou non : à zéro, ils sortent simplement de la marge
    sans qu'aucune erreur ne soit levée. Informatif — zéro reste un choix
    légitime (frais inclus par le transitaire, aucune police souscrite) — mais
    c'est un choix à faire sciemment, pas un défaut à découvrir après coup.
    """
    customs_places = (
        await session.exec(select(Place).where(col(Place.customs_clearance).is_(True)))
    ).all()
    configured = [
        place
        for place in customs_places
        if place.customs_declaration_fee and place.customs_declaration_fee > 0
    ]

    return Check(
        "Coûts d'import paramétrés",
        (
            f"frais de déclaration : {len(configured)}/{len(customs_places)} "
            f"lieu(x) de dédouanement ; assurance : "
            f"{settings.INSURANCE_RATE_PCT} % (0 = non facturée)"
        ),
        True,
        (
            "Renseigner places.customs_declaration_fee sur le lieu de "
            "dédouanement (facturé une fois par expédition) et "
            "INSURANCE_RATE_PCT au taux réel de la police."
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
            await _check_publication(session),
            await _check_fx_rates(session),
            await _check_import_cost_parameters(session),
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
