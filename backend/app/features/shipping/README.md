# Système de Livraison Multi-Segments

Ce module gère un système de livraison e-commerce flexible supportant les livraisons directes, le dropshipping hybride et les routes multi-segments avec consolidation intelligente.

## 🏗️ Architecture

Le système est conçu pour gérer des workflows complexes comme :
- **Livraison directe** : Entrepôt → Client (Tahiti)
- **Dropshipping hybride** : Fournisseur → Entrepôt → Client (France → Tahiti → Rangiroa)
- **Consolidation** : Regroupement de colis sur routes communes
- **Multi-modal** : Air, mer, route selon destination et contraintes

### Entités principales

#### 🏢 **Référentiels**
- **Partner** : Clients et fournisseurs (Ingram, clients Rangiroa...)
- **Place** : Lieux physiques (aéroports, ports, entrepôts, adresses)
- **StatusDefinition** : Statuts configurables par type d'entité
- **StatusTransition** : Règles de transitions entre statuts

#### 🛣️ **Routes et Étapes**
- **ShippingRoute** : Route logistique réutilisable (France → Tahiti)
- **ShippingRouteStep** : Étapes séquencées (CDG → PPT → Rangiroa)

#### 📦 **Consolidation**
- **ShippingRouteConsolidation** : Regroupement opérationnel (vol AF076 du jour)
- **ShippingOrderConsolidation** : Liaison commande ↔ regroupement

#### 🔍 **Suivi**
- **TrackingEvent** : Journal inviolable des changements
- **ShippingOrderStepConsolidation** : Suivi par étape et commande

#### 🚚 **Livraison finale**
- **DeliveryTask** : Tâche de livraison dernier kilomètre
- **Package** : Gestion des colis multiples

## 🎯 Cas d'Usage : Client Rangiroa

### Scénario : Commande produit Ingram France

Un client de Rangiroa achète un produit du fournisseur Ingram en France.

**Choix de livraison proposés :**
1. **Express** : France →[avion]→ Tahiti →[avion]→ Rangiroa (3 jours, +empreinte carbone, ++)
2. **Économique** : France →[bateau]→ Tahiti →[bateau]→ Rangiroa (21 jours, empreinte carbone, €)

### Configuration des Entités

#### 1. **Partenaires**

```python
from app.features.shipping.crud import crud_partner

# Fournisseur Ingram Micro France
ingram_data = {
    "name": "Ingram Micro France",
    "is_supplier": True,
    "email": "logistics@ingrammicro.fr",
    "country": "FR",
    "city": "Paris",
}
ingram = await crud_partner.create(session, obj_in=ingram_data)

# Client final à Rangiroa
client_data = {
    "name": "Jean Dupont",
    "is_customer": True,
    "email": "jean@rangiroa.pf",
    "country": "PF", 
    "city": "Rangiroa",
    "address_line1": "Avatoru, Rangiroa",
}
client = await crud_partner.create(session, obj_in=client_data)
```

#### 2. **Lieux Physiques**

```python
from app.features.shipping.crud import crud_place

# Entrepôt Ingram France
ingram_warehouse_data = {
    "name": "Entrepôt Ingram Paris",
    "type": "warehouse",
    "code": "INGRAM-CDG",
    "country": "FR",
    "city": "Roissy-en-France",
    "is_warehouse": True,
    "customs_clearance": False,
    "consolidation_service": True,
}
ingram_warehouse = await crud_place.create(session, obj_in=ingram_warehouse_data)

# Aéroport Charles de Gaulle
cdg_data = {
    "name": "Aéroport Charles de Gaulle",
    "type": "airport", 
    "code": "CDG",
    "country": "FR",
    "city": "Paris",
    "latitude": 49.0097,
    "longitude": 2.5479,
}
cdg = await crud_place.create(session, obj_in=cdg_data)

# Entrepôt Tahiti (hub)
tahiti_hub_data = {
    "name": "Hub Distribution Tahiti",
    "type": "warehouse",
    "code": "HUB-PPT",
    "country": "PF",
    "city": "Faaa",
    "is_warehouse": True,
    "customs_clearance": True,
    "consolidation_service": True,
    "repackaging_service": True,
}
tahiti_hub = await crud_place.create(session, obj_in=tahiti_hub_data)

# Aéroport de Tahiti
ppt_data = {
    "name": "Aéroport de Tahiti-Faa'a",
    "type": "airport",
    "code": "PPT", 
    "country": "PF",
    "city": "Faaa",
}
ppt = await crud_place.create(session, obj_in=ppt_data)

# Aéroport de Rangiroa
rrr_data = {
    "name": "Aéroport de Rangiroa",
    "type": "airport",
    "code": "RRR",
    "country": "PF", 
    "city": "Rangiroa",
}
rrr = await crud_place.create(session, obj_in=rrr_data)

# Adresse client Rangiroa
client_address_data = {
    "name": "Domicile Jean Dupont",
    "type": "address",
    "country": "PF",
    "city": "Rangiroa",
    "address_line1": "Avatoru, Rangiroa",
}
client_address = await crud_place.create(session, obj_in=client_address_data)
```

#### 3. **Routes avec Étapes**

```python
from app.features.shipping.crud import crud_shipping_route, crud_shipping_route_step

# Route Express : France → Tahiti
route_express_fr_tahiti_data = {
    "name": "Express France → Tahiti", 
    "from_place_id": ingram_warehouse.id,
    "to_place_id": tahiti_hub.id,
    "from_partner_id": ingram.id,
    "is_to_customer": False,  # Route intermédiaire (non client final)
    "allow_consolidation": True,
    "mode": "air",
    "operator": "Air France",
    "base_price": 45.00,
    "price_per_kg": 12.00,
    "carbon_footprint_kg_co2e": 2.8,
    "eta_days": 2,
}
route_express_fr_tahiti = await crud_shipping_route.create(session, obj_in=route_express_fr_tahiti_data)

# Étapes de la route express
# Étape 1 : Entrepôt → CDG
step1_data = {
    "route_id": route_express_fr_tahiti.id,
    "sequence": 1,
    "from_place_id": ingram_warehouse.id,
    "to_place_id": cdg.id,
    "mode": "road",
    "operator": "Chronopost",
    "eta_days": 1,
}
await crud_shipping_route_step.create(session, obj_in=step1_data)

# Étape 2 : CDG → PPT
step2_data = {
    "route_id": route_express_fr_tahiti.id,
    "sequence": 2,
    "from_place_id": cdg.id,
    "to_place_id": ppt.id,
    "mode": "air",
    "operator": "Air France",
    "operator_ref": "AF072",
    "eta_days": 1,
}
await crud_shipping_route_step.create(session, obj_in=step2_data)

# Route finale : Tahiti → Rangiroa (Express)
route_tahiti_rangiroa_express_data = {
    "name": "Tahiti → Rangiroa Express",
    "from_place_id": tahiti_hub.id,
    "to_place_id": client_address.id,
    "to_partner_id": client.id,
    "is_to_customer": True,  # Route vers client final
    "allow_consolidation": True,
    "mode": "air",
    "operator": "Air Tahiti",
    "base_price": 25.00,
    "carbon_footprint_kg_co2e": 0.8,
    "eta_days": 1,
}
route_tahiti_rangiroa_express = await crud_shipping_route.create(session, obj_in=route_tahiti_rangiroa_express_data)

# Étapes Tahiti → Rangiroa
# Étape 1 : Hub → PPT
step_hub_ppt_data = {
    "route_id": route_tahiti_rangiroa_express.id,
    "sequence": 1,
    "from_place_id": tahiti_hub.id,
    "to_place_id": ppt.id,
    "mode": "road",
    "operator": "Transport Local",
    "eta_days": 0,  # Même jour
}
await crud_shipping_route_step.create(session, obj_in=step_hub_ppt_data)

# Étape 2 : PPT → RRR
step_ppt_rrr_data = {
    "route_id": route_tahiti_rangiroa_express.id,
    "sequence": 2, 
    "from_place_id": ppt.id,
    "to_place_id": rrr.id,
    "mode": "air",
    "operator": "Air Tahiti",
    "operator_ref": "VT234",
    "eta_days": 1,
}
await crud_shipping_route_step.create(session, obj_in=step_ppt_rrr_data)

# Étape 3 : Aéroport → Domicile
step_delivery_data = {
    "route_id": route_tahiti_rangiroa_express.id,
    "sequence": 3,
    "from_place_id": rrr.id,
    "to_place_id": client_address.id,
    "mode": "road",
    "operator": "Livraison Locale",
    "eta_days": 0,  # Même jour
}
await crud_shipping_route_step.create(session, obj_in=step_delivery_data)
```

### 4. **Consolidations et Regroupements**

```python
from app.features.shipping.crud import crud_shipping_route_consolidation

# Créer une consolidation pour la route France → Tahiti
consolidation_data = {
    "route_id": route_express_fr_tahiti.id,
    "consolidation_code": "AF072-20251001",
    "name": "Vol AF072 - 1er Octobre 2025",
    "departure_planned_at": datetime(2025, 10, 1, 14, 30),  # 14h30
    "arrival_planned_at": datetime(2025, 10, 2, 6, 45),     # 06h45 (+1 jour)
    "cutoff_datetime": datetime(2025, 10, 1, 8, 0),        # Limite 08h00
    "max_weight_kg": 2000.0,
    "max_volume_m3": 15.0,
    "status_code": "open",
}
consolidation = await crud_shipping_route_consolidation.create(session, obj_in=consolidation_data)
```

### 5. **Liaison Commande ↔ Consolidation**

```python
from app.features.shipping.crud import crud_shipping_order_consolidation

# Lier une commande à la consolidation
order_link_data = {
    "consolidation_id": consolidation.id,
    "order_id": "12345678-1234-1234-1234-123456789abc",  # ID de votre commande
    "package_qty": 1,
    "weight_kg": 2.5,
    "volume_m3": 0.008,  # 20x20x20cm
    "agreed_shipping_price": 57.00,  # 45 + 12*2.5 = 75€
    "agreed_currency": "EUR",
    "idempotency_key": "order-123-route-456",
}
order_link = await crud_shipping_order_consolidation.create(session, obj_in=order_link_data)
```

## 📊 Suivi Client : "Où est mon colis ?"

### Interface Client - Résumé de Commande

```python
async def get_order_tracking_summary(order_id: str):
    # 1. Récupérer les liaisons consolidation
    order_links = await crud_shipping_order_consolidation.get_by_order(session, order_id)
    
    # 2. Pour chaque segment, récupérer le statut actuel
    tracking_summary = {
        "order_id": order_id,
        "segments": []
    }
    
    for link in order_links:
        # Récupérer la consolidation et sa route
        consolidation = await crud_shipping_route_consolidation.read(session, link.consolidation_id)
        route = await crud_shipping_route.read(session, consolidation.route_id)
        
        # Statut actuel du segment
        segment_info = {
            "route_name": route.name,
            "status": consolidation.status_code,
            "is_to_customer": route.is_to_customer,
            "current_location": None,
            "progress_percentage": 0,
        }
        
        # Récupérer les étapes et leur progression
        steps = await crud_shipping_route_step.get_steps_for_route(session, route.id)
        step_tracking = await crud_shipping_order_step_consolidation.get_by_order_and_consolidation(
            session, order_id, consolidation.id
        )
        
        completed_steps = len([s for s in step_tracking if s.is_done])
        segment_info["progress_percentage"] = (completed_steps / len(steps)) * 100
        
        # Dernière position connue
        if step_tracking:
            last_step = max(step_tracking, key=lambda s: s.last_event_at or s.created_at)
            step = await crud_shipping_route_step.read(session, last_step.route_step_id)
            place = await crud_place.read(session, step.to_place_id)
            segment_info["current_location"] = place.name
        
        tracking_summary["segments"].append(segment_info)
    
    return tracking_summary

# Exemple de réponse
{
    "order_id": "12345678-1234-1234-1234-123456789abc",
    "segments": [
        {
            "route_name": "Express France → Tahiti",
            "status": "in_transit", 
            "is_to_customer": False,
            "current_location": "Aéroport Charles de Gaulle",
            "progress_percentage": 50
        },
        {
            "route_name": "Tahiti → Rangiroa Express",
            "status": "pending",
            "is_to_customer": True, 
            "current_location": null,
            "progress_percentage": 0
        }
    ]
}
```

## 🔧 Administration des Ventes

### Regroupement de Colis

```python
# Voir tous les colis d'une consolidation
async def get_consolidation_manifest(consolidation_id: str):
    consolidation = await crud_shipping_route_consolidation.read(session, consolidation_id)
    order_links = await crud_shipping_order_consolidation.get_by_consolidation(session, consolidation_id)
    
    manifest = {
        "consolidation": {
            "code": consolidation.consolidation_code,
            "name": consolidation.name,
            "status": consolidation.status_code,
            "departure_planned": consolidation.departure_planned_at,
            "total_packages": consolidation.total_packages,
            "total_weight_kg": consolidation.total_weight_kg,
        },
        "orders": []
    }
    
    for link in order_links:
        # TODO: Récupérer les détails de la commande depuis votre système
        manifest["orders"].append({
            "order_id": link.order_id,
            "package_qty": link.package_qty,
            "weight_kg": link.weight_kg,
            "agreed_price": link.agreed_shipping_price,
            "status": link.status_code,
        })
    
    return manifest
```

### Mise à Jour de Statuts

```python
from app.features.shipping.crud import crud_tracking_event

# Mettre à jour le statut d'une consolidation
async def update_consolidation_status(consolidation_id: str, new_status: str, actor: str):
    consolidation = await crud_shipping_route_consolidation.read(session, consolidation_id)
    
    # Créer un événement de tracking
    await crud_tracking_event.create_tracking_event(
        session,
        subject_type="consolidation",
        subject_id=consolidation_id,
        status_from=consolidation.status_code,
        status_to=new_status,
        actor=actor,
        description=f"Statut mis à jour par {actor}"
    )
    
    # Mettre à jour la consolidation
    await crud_shipping_route_consolidation.update(
        session,
        db_obj=consolidation,
        obj_in={"status_code": new_status}
    )
```

### Livraisons à Effectuer

```python
# Obtenir toutes les tâches de livraison à domicile
async def get_home_deliveries_for_today():
    today_start = datetime.now().replace(hour=0, minute=0, second=0)
    today_end = datetime.now().replace(hour=23, minute=59, second=59)
    
    tasks = await crud_delivery_task.get_tasks_by_window(
        session,
        start_datetime=today_start,
        end_datetime=today_end
    )
    
    delivery_list = []
    for task in tasks:
        if task.delivery_type == "home_delivery":
            # Récupérer l'adresse
            address_place = await crud_place.read(session, task.address_place_id)
            
            delivery_list.append({
                "task_id": task.id,
                "order_id": task.order_id,
                "customer_name": address_place.name,
                "address": f"{address_place.address_line1}, {address_place.city}",
                "time_window": f"{task.window_start} - {task.window_end}",
                "status": task.status_code,
                "assignee": task.assignee,
                "instructions": task.delivery_instructions,
            })
    
    return delivery_list
```

## 🚀 Avantages du Système

### ✅ **Flexibilité Maximum**
- Routes intermédiaires configurables
- Étapes séquencées pour routing complexe
- Support multi-modal (air/mer/route)

### ✅ **Consolidation Intelligente** 
- Regroupement automatique par route
- Optimisation des coûts de transport
- Gestion des dates limites

### ✅ **Traçabilité Complète**
- Journal inviolable des événements
- Suivi par étape et par commande
- Preuves de livraison

### ✅ **Gestion Opérationnelle**
- Tableaux de bord consolidation
- Planification des livraisons
- Métriques carbone et coûts

## 📈 Extensibilité

Le système peut facilement s'adapter à :
- **Nouveaux modes de transport** (drone, véhicule autonome)
- **Nouvelles destinations** (Marquises, Australes)
- **Intégrations API** transporteurs (DHL, Air Tahiti...)
- **Règles métier complexes** (douanes, restrictions)

Cette architecture modulaire garantit une évolutivité maximale pour votre écosystème e-commerce polynésien ! 🏝️