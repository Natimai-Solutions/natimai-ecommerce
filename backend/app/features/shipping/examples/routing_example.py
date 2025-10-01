"""
Exemple d'utilisation des nouvelles fonctionnalités de routage shipping.

Ce fichier montre comment utiliser l'algorithme de recherche de chemins
pour trouver toutes les routes possibles entre deux lieux.
"""

import uuid

from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.shipping.crud.route import crud_shipping_route


async def example_routing_usage(session: AsyncSession):
    """
    Exemple complet d'utilisation des fonctionnalités de routage
    """

    # IDs d'exemple (à remplacer par de vrais IDs)
    warehouse_paris = uuid.uuid4()  # Entrepôt Paris
    hub_lyon = uuid.uuid4()  # Hub Lyon
    customer_marseille = uuid.uuid4()  # Client Marseille

    print("=== EXEMPLE: Recherche de chemins de livraison ===\n")

    # 1. Trouver tous les chemins possibles
    print("1. Recherche de tous les chemins Paris -> Marseille:")
    all_paths = await crud_shipping_route.get_routes_between_places(
        session=session,
        from_place_id=warehouse_paris,
        to_place_id=customer_marseille,
        is_to_customer=True,
        max_hops=5,
    )

    print(f"   Nombre de chemins trouvés: {len(all_paths)}")
    for i, path in enumerate(all_paths):
        hops = len(path)
        operators = [route.operator for route in path if route.operator]
        print(f"   Chemin {i + 1}: {hops} étapes, opérateurs: {operators}")

    print()

    # 2. Obtenir le chemin optimal
    print("2. Recherche du chemin optimal:")
    optimal_path = await crud_shipping_route.get_optimal_route_between_places(
        session=session,
        from_place_id=warehouse_paris,
        to_place_id=customer_marseille,
        prefer_direct=True,
    )

    if optimal_path:
        print(f"   Chemin optimal trouvé: {len(optimal_path)} étapes")
        for i, route in enumerate(optimal_path):
            print(f"   Étape {i + 1}: {route.name} (priorité: {route.priority})")
    else:
        print("   Aucun chemin optimal trouvé")

    print()

    # 3. Obtenir les statistiques
    print("3. Statistiques de routage:")
    stats = await crud_shipping_route.get_routing_statistics(
        session=session, from_place_id=warehouse_paris, to_place_id=customer_marseille
    )

    print(f"   Total chemins: {stats['total_paths']}")
    print(f"   Chemins directs: {stats['direct_paths']}")
    print(f"   Étapes min/max: {stats['min_hops']}/{stats['max_hops']}")
    print(f"   Moyenne étapes: {stats['avg_hops']:.1f}")
    print(f"   Route directe disponible: {stats['has_direct_route']}")

    print("\n=== FIN EXEMPLE ===")


# Exemples d'usage des endpoints API
API_USAGE_EXAMPLES = """
=== EXEMPLES D'APPELS API ===

1. Récupérer tous les chemins entre deux lieux:
   GET /api/v1/shipping/shipping_route/paths/{from_place_id}/{to_place_id}
   Query params: is_to_customer, max_hops

2. Obtenir le chemin optimal:
   GET /api/v1/shipping/shipping_route/optimal/{from_place_id}/{to_place_id}
   Query params: is_to_customer, prefer_direct

3. Statistiques de routage:
   GET /api/v1/shipping/shipping_route/statistics/{from_place_id}/{to_place_id}
   Query params: is_to_customer

=== RÉPONSES TYPES ===

RoutePathsResponse:
{
  "paths": [
    {
      "hops": 1,
      "routes": [...],
      "total_priority": 10.0,
      "operators": ["DHL", "FedEx"]
    }
  ],
  "total_count": 3
}

RoutingStatisticsResponse:
{
  "total_paths": 5,
  "direct_paths": 2,
  "min_hops": 1,
  "max_hops": 3,
  "avg_hops": 1.8,
  "has_direct_route": true,
  "path_details": [...]
}
"""

if __name__ == "__main__":
    print(API_USAGE_EXAMPLES)
