# Cahier des charges — Routage shipping multi-fournisseurs (v2)

> **Statut : à implémenter.** Cette v2 remplace la v1 rédigée par Codex. Le
> changement structurant : on raisonne désormais en **tronçons mutualisés
> sélectionnables** (et non plus en « chemins complets pré-calculés et classés »).
>
> **Décisions actées :**
> 1. **Fusion forcée** des sous-expéditions aux hubs (§3.4).
> 2. **Lien produit ↔ fournisseur par FK dure** : `Product.supplier_partner_id` +
>    `Partner.default_origin_place_id` + `Product.origin_place_id` optionnel (§2.2).
> 3. **Référentiel géographique normalisé** (`GeoCountry` / `GeoRegion` / `GeoTown`)
>    avec `Address.geo_town_id`, `Place.geo_town_id` / `geo_country_id` — c'est un
>    sous-projet prérequis (§2.4, Lot 1a).
> 4. **Pas de scopes géo wildcard sur `ShippingRoute`** : tout passe par
>    routes-au-Place + override `from_partner_id` (§2.3).
> 5. **Coupure nette du checkout** : `CheckoutRequest.shipping_route_ids` est
>    **supprimé** et remplacé par `shipping_selections` ; front + admin + tests
>    adaptés dans le même lot (§5.3, Lot 4).

---

## 1. Contexte et objectif

Un panier peut contenir des produits provenant de **plusieurs origines** :
- des fournisseurs distants (ex. Fournisseur 1 à Toulouse, Fournisseur 2 à Strasbourg) ;
- du stock local Natimai (entrepôt Papeete).

Le système doit, à partir du contenu du panier et de la destination client :
1. découper la livraison en **sous-expéditions** (une par origine) ;
2. proposer pour chaque **tronçon** (segment `origine → destination` du parcours) un
   petit nombre d'options (modes), en **mutualisant** les tronçons communs entre
   sous-expéditions ;
3. **auto-sélectionner** les tronçons qui n'ont qu'une option (ou qui sont
   « back-office ») et ne laisser au client que les vrais points de choix ;
4. permettre des **routes spécifiques fournisseur** (tarifs particuliers) en
   override des routes génériques, sans dupliquer manuellement les routes communes ;
5. chiffrer le tout (coût détaillé par tronçon et par sous-expédition, ETA,
   empreinte carbone) en réutilisant le moteur de pricing existant.

### Cas de référence

```
F1 (Toulouse) ──┐
                ├─► CDG ──► Papeete ──► Arutua (client)
F2 (Strasbourg) ┘                ▲
F3 = Natimai (entrepôt Papeete) ─┘
```

Tronçons présentés au checkout pour ce panier :

| Tronçon            | Sous-expéditions concernées | Options                              | Visibilité      |
|--------------------|-----------------------------|--------------------------------------|-----------------|
| Toulouse → CDG     | F1                          | (1 route) → auto                     | masqué          |
| Strasbourg → CDG   | F2                          | (1 route) → auto                     | masqué          |
| **CDG → Papeete**  | F1 **+** F2 (fusionnés)     | Avion (1 sem.) / Bateau (2 mois)     | **choix client**|
| **Dernier tronçon (depuis Papeete)** | F1 + F2 + F3 (fusionnés)  | Livraison Arutua avion / Livraison Arutua bateau / **Retrait boutique Papeete** | **choix client**|

Le client ne voit que 2 décisions réelles ; les tronçons amont sont automatiques.
Le **retrait en boutique est systématiquement proposé** sur le dernier tronçon
(cf. §3.9) : en PF, beaucoup de clients d'îles éloignées passent régulièrement à
Papeete (courses, médecin…) ou y ont de la famille qui récupère le colis.

---

## 2. Modèle de données

### 2.1 Place (existant — + 2 FK vers le référentiel géo)

`Place` représente déjà tout nœud physique (aéroport, port, entrepôt, île,
adresse, boutique) avec `type`, `code`, `city`, `country`, `region`, `partner_id`,
`is_owned`. Les hubs du parcours sont des `Place` : *Toulouse hub*, *Strasbourg
hub*, *CDG*, *entrepôt Papeete*, *Arutua*, *Boutique Papeete*.

À **ajouter** (pour relier au référentiel géo, §2.4) :
- `Place.geo_country_id: uuid | None` (FK `geo_countries.id`) ;
- `Place.geo_town_id: uuid | None` (FK `geo_towns.id`) — la commune/île du lieu ;
- `Place.is_delivery_destination: bool = false` — ce `Place` peut-il être la
  destination finale d'une livraison client ? (distingue, dans une même commune, le
  nœud « adresse client » du nœud « entrepôt » / « boutique » / « aéroport »).

Les colonnes string existantes (`city`, `country`, `region`) restent pour
l'affichage / la transition ; à terme dérivées du référentiel.

### 2.2 Origine d'une sous-expédition — FK produit ↔ fournisseur (décidé)

Une sous-expédition doit résoudre **son Place d'origine**. Champs à **ajouter** :

- `Product.supplier_partner_id: uuid | None` (FK `partners.id`) — le fournisseur du
  produit (null pour un produit local). Renseigné à la synchro fournisseur ;
  back-fill depuis `supplier_name` (un `Partner` par `supplier_name`).
- `Partner.default_origin_place_id: uuid | None` (FK `places.id`) — le `Place`
  d'expédition par défaut du fournisseur.
- `Product.origin_place_id: uuid | None` (FK `places.id`, optionnel) — override par
  produit si un fournisseur expédie de plusieurs sites.

`supplier_name` (string machine) reste la clé technique de la synchro
multi-fournisseurs ; `supplier_partner_id` est le pont vers le routage (et c'est lui
que matchent les routes override `from_partner_id`).

Règle de résolution de l'origine d'une ligne de panier :
`Product.origin_place_id` → sinon `Partner.default_origin_place_id` (via
`Product.supplier_partner_id`) → sinon, si servie en stock local, `Inventory.place_id`
→ sinon : ligne **non routable** (sa sous-expédition est listée dans `unroutable[]`,
cf. §3.3 / §4.2).

### 2.3 ShippingRoute (existant — sémantique précisée + 2 champs)

On conserve tous les champs actuels (`from_place_id`, `to_place_id`,
`from_partner_id`, `to_partner_id`, `mode`, `operator`, `base_price`,
`price_per_kg`, `eta_days`, `carbon_footprint_kg_co2e`, `allow_consolidation`,
`is_to_customer`, `priority`, `status_code`, `is_active`, `route_metadata`, …).

Précisions de sémantique :

- **`from_partner_id` = null** → route **générique** : valable pour toute
  sous-expédition dont l'origine est `from_place_id`, quel que soit le fournisseur.
- **`from_partner_id` = `Fx`** → route **override** : ne s'applique qu'aux
  articles de `Fx`, et **masque** la route générique de même `(from_place, to_place)`
  pour cette sous-expédition. Voir §3.6 pour la portée (uniquement sur la partie
  « privée » amont d'une sous-expédition, jamais sur un tronçon déjà mutualisé).
- **`allow_consolidation`** → ce tronçon accepte la fusion avec d'autres
  sous-expéditions à son `to_place`. Avec la fusion forcée (§3.4), c'est en
  pratique toujours `true` ; le flag reste pour pouvoir, plus tard, exclure une
  route exceptionnelle de la mutualisation sans re-migrer.
- **`is_to_customer`** → tronçon de dernier kilomètre (vers le client / la boutique).

Champs à **ajouter** :

- **`is_customer_selectable: bool = true`** — la route apparaît-elle comme option
  proposée au client ? Un tronçon dont **toutes** les routes ont
  `is_customer_selectable = false` est **masqué** et utilise sa route `is_default`.
- **`is_default: bool = false`** — route retenue pour le devis automatique quand
  aucun choix client n'est fait, ou quand le tronçon est masqué. Exactement une
  route `is_default = true` par tronçon est attendue ; à défaut, le moteur prend
  la route de plus petit `priority`.

**Pas de scopes géo wildcard sur les routes (décidé).** Une route est strictement
`from_place → to_place`. Toute la mutualisation passe par : routes au niveau `Place`
(génériques) + override `from_partner_id`. Si un jour on veut une route « générique
vers toute une zone » (ex. « Papeete → tout archipel des Tuamotu à un tarif »), ce
sera une évolution dédiée (§11), pas un champ ajouté maintenant.

### 2.4 Référentiel géographique + destination client (décidé — sous-projet prérequis)

Remplacer le texte libre des adresses par un **référentiel géographique normalisé**,
hiérarchique :

- **`GeoCountry`** : pays (code ISO-2, nom).
- **`GeoRegion`** : subdivision (archipel / état / département) — `country_id` FK.
- **`GeoTown`** : commune / ville / île / village — `region_id` FK, `type`
  (`commune` / `island` / `village` / …), code(s) éventuel(s).

Liaisons :
- **`Address.geo_town_id: uuid`** (FK `geo_towns.id`) — remplace l'usage métier de
  `Address.city` / `state` / `country` (qui restent en colonnes dénormalisées pour
  l'affichage / la transition). `Address.street` / `postal_code` conservent le
  détail rue.
- **`Place.geo_town_id` / `Place.geo_country_id`** (cf. §2.1).

**Résolution de la destination du moteur** : depuis `Address.geo_town_id`, trouver
le `Place` tel que `Place.geo_town_id == Address.geo_town_id` **et**
`Place.is_delivery_destination == true`. Si aucun → la commune n'est pas (encore)
desservie en livraison « home » → destination « non desservie » (non bloquant si un
retrait boutique est retenu, §6). Si plusieurs → départage déterministe (le
`Place` `type == 'address'`, sinon le plus prioritaire) + `trace`.

> Ceci remplace l'heuristique string actuelle (`_PF_ADDRESS_MARKERS`,
> `_is_polynesia_shipping_address` dans `cart.py`).
>
> **Périmètre du sous-projet (Lot 1a)** : tables `GeoCountry` / `GeoRegion` /
> `GeoTown` + import des données (au minimum la PF : pays, archipels, communes,
> îles habitées) ; colonnes `Address.geo_town_id`, `Place.geo_town_id` /
> `geo_country_id` / `is_delivery_destination` ; **migration des adresses
> existantes** (match best-effort `(country, state, city)` string → `GeoTown` ;
> non-résolues marquées pour revue) ; endpoints + écrans admin de gestion ;
> sélecteur commune/île côté front à la saisie d'adresse. Le moteur de routage (Lots
> 2-4) dépend de ce lot.

### 2.5 Exécution / suivi : aucun changement de schéma

Le suivi post-checkout réutilise tel quel `ShippingRouteTracking` (chaîne linéaire
par `sequence_order`) et `ShippingRouteTrackingConsolidation` :

- chaque **sous-expédition** = une chaîne de `ShippingRouteTracking` (un par
  tronçon de son parcours, `sequence_order` 1..n) ;
- les **tronçons mutualisés** (≥ 2 sous-expéditions) : tous les trackings de ces
  sous-expéditions sur ce tronçon pointent vers la **même**
  `ShippingRouteTrackingConsolidation` (clé logique `(route_id, order_id)` ; un
  tracking par sous-expédition reste créé pour conserver le `sequence_order` propre
  à chaque parcours). Le statut de la consolidation pilote ces trackings.

Pas de graphe parent/enfant à introduire : le modèle linéaire + consolidation
suffit dès lors que la fusion est forcée.

---

## 3. Moteur de routage

### 3.1 Entrées

- `cart_id` (obligatoire).
- `destination_place_id` (optionnel ; sinon résolu depuis l'adresse de livraison
  de la commande/du panier — §2.4).
- `include_pickup` (optionnel, défaut `true`).
- `selections: { leg_key → route_id }` (optionnel ; pour le re-quote, §5.2).
- Paramètres de chiffrage : `total_weight_kg`, `declared_value`, `currency`,
  `as_of` (optionnels ; si absents, le moteur renvoie les tronçons sans chiffrage).

### 3.2 Découpage en sous-expéditions

Regrouper les lignes du panier par **Place d'origine** (résolution §2.2). Chaque
groupe = une sous-expédition portant : `origin_place_id`, l'ensemble des
`supplier_id` (ou marqueur `local`), le poids facturable cumulé et la valeur
déclarée cumulée du groupe (pour le pricing par tronçon).

### 3.3 Construction du graphe par sous-expédition

Pour chaque sous-expédition, chercher les parcours `origin_place_id → destination`
par recherche orientée **en remontant depuis la destination** (réutiliser la
logique de `ShippingRouteCrud.get_routes_between_places` : cache des routes
arrivant à un Place, protection des cycles via `visited_places`, `max_hops`).

Routes candidates pour une sous-expédition : routes **actives** (`is_active` et
`status_code` exploitable) telles que `from_partner_id is null` **ou**
`from_partner_id ∈ supplier_id de la sous-expédition`. Pour un couple
`(from_place, to_place)` donné, si une route override existe pour ce fournisseur,
elle **masque** la générique pour cette sous-expédition (sous réserve §3.6).

Si une sous-expédition n'a **aucun** parcours → elle est listée dans `unroutable[]`
avec la raison ; le reste de la réponse est quand même produit (§4.2).

### 3.4 Fusion forcée aux hubs (décision actée)

Deux sous-expéditions **fusionnent** dès qu'elles partagent un `Place`. À partir de
ce nœud commun, tous les tronçons aval sont **communs** : un seul choix de mode,
appliqué à l'ensemble du flux fusionné. C'est la consolidation par défaut (gain de
coût, moins de décisions client). Justification métier : le client se désintéresse
des tronçons amont (Toulouse→CDG en 1 ou 2 jours) ; ce qui l'intéresse, c'est le
tronçon international et le dernier kilomètre (Papeete→Arutua : avion ~1 sem. vs
bateau ~2 mois).

Quand une sous-expédition a **plusieurs parcours candidats**, le moteur retient
**celui qui converge le plus tôt vers un hub partagé** (consolidation maximale). Un
parcours alternatif n'est exposé que si une route le marque explicitement
(évolution future ; non requis au MVP).

### 3.5 Réduction en tronçons (legs)

Calculer l'union des couples `(from_place, to_place)` sur toutes les
sous-expéditions ⇒ liste de **tronçons**. Pour chaque tronçon :

- `leg_key` = identifiant stable (ex. `f"{from_place_id}->{to_place_id}"`).
- `from_place`, `to_place` ; `shipment_ids` = sous-expéditions qui l'empruntent.
- `options` = routes candidates de ce tronçon (cf. §3.6 pour le filtrage
  override/générique sur tronçon mutualisé).
- `default_route_id` = la route `is_default = true` du tronçon (sinon plus petit
  `priority`).
- `kind` :
  - `auto` si une seule `option`, **ou** si toutes les options ont
    `is_customer_selectable = false` → le tronçon est masqué dans l'UI, le devis
    utilise `default_route_id` ;
  - `customer_choice` si ≥ 2 options avec `is_customer_selectable = true`.
- Ordre : les tronçons sont ordonnés topologiquement (origine → … → destination)
  ; un tronçon mutualisé n'apparaît **qu'une fois**.

#### 3.5.1 Cas particulier du dernier tronçon (last-mile)

Le dernier kilomètre ne suit pas la règle `(from_place, to_place)` : « comment on
fait le dernier kilomètre » est **une seule décision** dont les options peuvent
avoir des `to_place` différents (livraison à domicile vs retrait en boutique A vs
retrait en boutique B). Donc :

- Pour chaque sous-expédition, on identifie son **hub final** (le dernier nœud
  partagé après fusion — ici *entrepôt Papeete*). Toutes les routes `is_to_customer
  = true` partant de ce hub forment **un unique tronçon « last-mile »**, avec
  `leg_key = f"last-mile@{hub_place_id}"`, `from_place_id = hub`, `to_place_id = null`
  (résolu par option).
- Chaque `option` de ce tronçon porte : `route_id`, `mode`, `eta_days`,
  `to_place_id` (destination effective de l'option), `delivery_type ∈ {home, pickup}`,
  et `pickup_place_id` si `pickup`.
- Options « home » candidates = routes `is_to_customer = true` du hub vers le
  `Place` destination résolu (§2.4 / §6). S'il n'y a pas de destination résolue,
  **aucune** option home (mais le pickup reste, cf. §3.9).
- Options « pickup » candidates = routes `mode = "pickup"` du hub vers une boutique
  — voir §3.9 pour la règle « toujours proposé / configurable ».

### 3.6 Portée des routes override fournisseur

Une route `from_partner_id = Fx` n'est honorée que sur la **partie privée amont**
d'une sous-expédition — c.-à-d. les tronçons situés **avant** le premier hub
partagé avec une autre sous-expédition. Sur un **tronçon déjà mutualisé**, seules
les routes **génériques** (`from_partner_id is null`) sont candidates. Rationnel :
un tarif spécial fournisseur sert à *amener ses marchandises jusqu'au hub* ; une
fois la marchandise consolidée, elle est acheminée et tarifée de façon générique.

### 3.7 Départage des routes d'un même tronçon

Comme il n'y a pas de scopes géo, la spécificité se réduit à **fournisseur vs
générique** :

1. Sur la **partie privée amont** d'une sous-expédition : une route override
   (`from_partner_id == Fx`) **masque** la route générique de même
   `(from_place, to_place)` ; s'il y en a plusieurs (override + variantes), elles
   sont toutes des `options` du tronçon (sauf `is_customer_selectable = false`).
2. Choix de la **route `default`** d'un tronçon : la route `is_default = true` ;
   à défaut, la route de plus petit `priority` (puis ordre stable).

⚠️ Aucune de ces règles ne sert à *classer les options présentées au client* : ce
classement se fait par **prix / ETA / CO₂** (cf. la préférence
`CheckoutShippingPreference` déjà existante : `FASTEST` / `CHEAPEST` /
`ECO_FRIENDLY`).

### 3.8 Chiffrage

Réutiliser **strictement** l'existant : `calculate_shipping_for_routes(...)` →
`ShippingCostSummary` (avec `RouteShippingCostBreakdown` par route :
`fixed_fee` / `weight_fee` / `value_fee` / `total_fee`, `weight_unit`,
`billable_weight`, `eta_days`, `carbon_footprint_kg_co2e`, `pricing_effective`) et
les extras portés par `route_metadata` (`weight_unit`, `value_rate` /
`value_percent`, `min_total`, `max_total`, `effective_from` / `effective_until`).

- **Par sous-expédition** : appliquer le chiffrage à sa chaîne de routes
  sélectionnées (défauts ou `selections`), avec son poids/valeur propres.
- **Total panier** : somme des sous-expéditions, dans `currency`.
- **ETA** : agrégation déjà codée (somme des `eta_days` si tous renseignés, sinon
  `null`) — appliquée par sous-expédition ; l'ETA panier = max des sous-expéditions.
- Une route hors fenêtre `effective_*` reste **affichée** avec
  `pricing_effective = false` (comportement actuel conservé), elle n'est pas masquée.

### 3.9 Pickup / retrait en boutique

Modélisé comme une route de dernier kilomètre : `mode = "pickup"`,
`is_to_customer = true`, `from_place = <hub final>` (ex. *entrepôt Papeete*),
`to_place = <boutique>`, `price_per_kg = 0` (et `base_price` éventuel = frais de
mise à disposition). Elle entre dans la liste `options` du tronçon « last-mile »
(§3.5.1) comme les autres options.

**Règle de proposition — « toujours proposé », configurable :**

- **Comportement par défaut (cas PF)** : toute route `mode = "pickup"` dont le
  `from_place` est le hub final d'une sous-expédition est **systématiquement
  ajoutée** aux options du dernier tronçon, **indépendamment** de la destination du
  client — y compris si le client est sur une île éloignée et même si sa commune
  n'a pas pu être résolue. Justification : en PF, beaucoup de clients passent
  régulièrement à Papeete (courses, médecin…) ou y font récupérer le colis par un
  proche ; le retrait est donc toujours utile.
- **Restriction (autres contextes)** : pour limiter le retrait à certaines zones,
  basculer le réglage global `SHIPPING_PICKUP_ALWAYS_OFFERED` (§7.5) à `false` ; le
  pickup n'est alors proposé que si la boutique « dessert » la zone du client,
  défini par : même `GeoCountry` que la commune du client **et/ou** une liste
  explicite `Place.served_geo_town_ids` sur le `Place` boutique (champ à ajouter le
  moment venu — non requis au MVP PF).
- `include_pickup = false` dans la requête `by-cart` masque les options pickup
  pour cet appel uniquement (ex. tunnel d'achat sans retrait).
- Plusieurs boutiques ⇒ plusieurs options pickup (une par boutique atteignable
  depuis le hub) ; le client choisit laquelle.

**Conséquences quand une option pickup est retenue :**

- flag **`requires_pickup = true`** sur l'option (déduit de `mode == "pickup"`) :
  **pas de `DeliveryTask`**, et **pas d'adresse client requise** côté checkout — la
  destination « effective » de la commande est la boutique (`pickup_place_id`). Le
  `ShippingRouteTracking` du dernier tronçon a `address_id` = adresse de la boutique
  (ou un champ dédié `pickup_place_id`), pas l'adresse du client.
- la commune du client peut donc rester **non résolue** sans bloquer le checkout, à
  condition qu'une option pickup soit retenue (§6).

---

## 4. Endpoint principal

`POST /api/v1/shipping/route/options/by-cart`

### 4.1 Requête

```jsonc
{
  "cart_id": "uuid",
  "destination_geo_town_id": "uuid|null",  // optionnel ; défaut = commune de l'adresse de livraison du panier
  "destination_place_id": "uuid|null",     // optionnel ; override avancé (Place déjà résolu)
  "include_pickup": true,                   // optionnel, défaut true
  "total_weight_kg": "decimal|null",        // optionnel — active le chiffrage
  "declared_value": "decimal|null",         // optionnel
  "currency": "EUR|XPF|...",                // optionnel
  "as_of": "datetime|null"                  // optionnel
}
```

### 4.2 Réponse

```jsonc
{
  "destination_place_id": "uuid",
  "shipments": [
    {
      "shipment_id": "s1",
      "origin_place_id": "uuid-toulouse",
      "supplier_ids": ["uuid-f1"],          // ou ["local"]
      "leg_keys": ["toulouse->cdg", "cdg->ppt", "ppt->arutua"],
      "billable_weight_kg": "decimal",
      "declared_value": "decimal"
    }
    // ... s2 (Strasbourg), s3 (local Papeete)
  ],
  "legs": [
    {
      "leg_key": "toulouse->cdg",
      "from_place_id": "uuid", "to_place_id": "uuid",
      "shipment_ids": ["s1"],
      "kind": "auto",                        // masqué dans l'UI
      "default_route_id": "uuid",
      "options": [ { "route_id": "uuid", "name": "...", "mode": "air",
                     "operator": "...", "eta_days": 2,
                     "carbon_footprint_kg_co2e": 12.0,
                     "is_customer_selectable": false, "is_default": true } ]
    },
    {
      "leg_key": "cdg->ppt",
      "from_place_id": "uuid", "to_place_id": "uuid",
      "shipment_ids": ["s1", "s2"],          // FUSIONNÉ
      "kind": "customer_choice",
      "default_route_id": "uuid-air",
      "options": [
        { "route_id": "uuid-air", "mode": "air", "eta_days": 7,  "is_customer_selectable": true, "is_default": true },
        { "route_id": "uuid-sea", "mode": "sea", "eta_days": 60, "is_customer_selectable": true, "is_default": false }
      ]
    },
    {
      "leg_key": "last-mile@uuid-ppt-hub",   // dernier tronçon — §3.5.1
      "from_place_id": "uuid-ppt-hub", "to_place_id": null,  // résolu par option
      "shipment_ids": ["s1", "s2", "s3"],    // FUSIONNÉ (tous)
      "kind": "customer_choice",
      "default_route_id": "uuid-air-domestic",
      "options": [
        { "route_id": "uuid-air-domestic", "mode": "air",    "eta_days": 1,
          "delivery_type": "home",   "to_place_id": "uuid-arutua" },
        { "route_id": "uuid-sea-domestic", "mode": "sea",    "eta_days": 14,
          "delivery_type": "home",   "to_place_id": "uuid-arutua" },
        { "route_id": "uuid-pickup-ppt",   "mode": "pickup", "eta_days": 0,
          "delivery_type": "pickup", "to_place_id": "uuid-boutique-ppt",
          "pickup_place_id": "uuid-boutique-ppt", "requires_pickup": true }
        // ... une option pickup par boutique atteignable ; toujours présentes
        //     (sauf include_pickup=false), même si destination_place_id non résolu
      ]
    }
  ],
  "quote": {                                 // ShippingCostSummary pour la combinaison par défaut
    "currency": "EUR",
    "total_fee": "decimal",
    "eta_days": 10,
    "carbon_footprint_kg_co2e": 42.0,
    "per_shipment": [ { "shipment_id": "s1", "total_fee": "decimal", "eta_days": 10,
                        "segments": [ /* RouteShippingCostBreakdown[] */ ] } ],
    "segments": [ /* breakdown global, ordre topologique */ ]
  },
  "unroutable": [ { "shipment_id": "s4", "origin_place_id": "uuid", "reason": "no path to destination" } ],
  "rejected_candidates": [ { "route_id": "uuid", "leg_key": "...", "reason": "inactive | partner mismatch | merged-leg (override ignored)" } ],
  "trace": [ /* observabilité : critères appliqués, scores, hubs de fusion détectés */ ]
}
```

`kind = "auto"` ⇒ le front masque le tronçon ; `kind = "customer_choice"` ⇒
sélecteur (par défaut sur `default_route_id`, tri des options selon la préférence
client prix/ETA/CO₂).

---

## 5. Re-quote et intégration checkout

### 5.1 Pourquoi un re-quote serveur

Le client choisit une route par tronçon `customer_choice` ; le total dépend de ces
choix. Le serveur doit recalculer (jamais faire confiance à un total client).

### 5.2 `POST /api/v1/shipping/route/quote-cart`

Requête : `{ cart_id, selections: { leg_key → route_id }, total_weight_kg?,
declared_value?, currency?, as_of? }`. Le serveur :

1. rejoue le moteur (§3) pour obtenir les sous-expéditions et tronçons ;
2. valide chaque `selections[leg_key]` : la route choisie doit être une `option`
   du tronçon ; tout tronçon `customer_choice` non fourni prend son
   `default_route_id` ; un tronçon `auto` ignore toute sélection ;
3. renvoie le **`ShippingCostSummary`** recalculé (total + `per_shipment` +
   `segments`), plus `applied_selections` (la map effectivement utilisée, défauts
   inclus).

Réutilise l'endpoint `/quote` existant en interne (même primitive de chiffrage).

### 5.3 Checkout (`cart.py`)

Refonte du checkout pour s'appuyer sur le moteur :

- `CheckoutRequest` : **supprimer** `shipping_route_ids` (coupure nette, décidé) et
  le remplacer par `shipping_selections: { leg_key → route_id }` (optionnel ; vide
  ⇒ tout en défaut). `shipping_preference` reste accepté : il sert à
  pré-sélectionner les `customer_choice` (tri prix/ETA/CO₂) si le client n'a rien
  choisi. Le client doit aussi fournir (ou avoir sur son adresse) un
  `geo_town_id` — sauf si toutes les sélections de dernier tronçon sont des pickups.
- Au checkout : appeler `quote-cart` (avec `applied_selections`) → en déduire le
  `ShippingCostSummary` → `order.shipping_fee_amount` / `order.shipping_cost_breakdown`
  (champ déjà existant) ; `applied_shipping_route_ids` dans la réponse = l'union des
  routes retenues.
- Persistance du suivi (§2.5) : pour chaque sous-expédition, créer la chaîne de
  `ShippingRouteTracking` (un par tronçon, `sequence_order` 1..n, `address_id` =
  destination — ou boutique si `requires_pickup`, statut initial = `pending` du
  lifecycle seedé au Lot 6) ; pour les tronçons mutualisés, rattacher tous les
  trackings concernés à une `ShippingRouteTrackingConsolidation` partagée (créée une
  fois par `(route_id, order_id)`).
- `DeliveryTask` : créée pour le dernier tronçon si l'option retenue est `home`
  (`delivery_type = home_delivery`, `address_id` = adresse client) ; **aucune** si
  l'option est `pickup` (`requires_pickup`). Cf. Lot 4 / Lot 6.
- **Suppression / remplacement de la logique actuelle** :
  `FulfillmentSegment` (`LOCAL` / `SUPPLIER_DIRECT` / `CONSOLIDATION_PF`),
  `_plan_checkout_fulfillment_segments`, `_select_supplier_segment`,
  `_is_polynesia_shipping_address`, `_PF_ADDRESS_MARKERS`,
  `_resolve_tracking_route_for_segment`, `_link_fulfillment_segments_to_tracking`,
  `_select_checkout_routes_by_preference` → remplacés par : résolution destination
  (§2.4) + moteur (§3) + persistance ci-dessus. La distinction « stock local vs
  fournisseur » devient simplement « origine = entrepôt Papeete vs origine =
  Place fournisseur » ; la « consolidation PF » devient un hub Papeete partagé.
- La réservation de stock (`_reserve_stock_for_checkout`) est conservée : seule la
  partie *routage / tracking* change. Le rattachement ligne ↔ sous-expédition se
  fait via l'origine résolue de la ligne.

---

## 6. Résolution de destination (détail)

1. Si la requête fournit `destination_place_id` → l'utiliser directement (override
   avancé).
2. Sinon, déterminer la **commune de destination** : `destination_geo_town_id` de la
   requête, sinon `Address.geo_town_id` de l'adresse de livraison du panier.
3. Depuis cette commune, résoudre le **`Place` de livraison** : `Place` tel que
   `geo_town_id == <commune>` **et** `is_delivery_destination == true`.
   - 1 résultat → l'utiliser.
   - ≥ 2 → départage déterministe (`type == 'address'` prioritaire, puis plus petit
     `priority`) + `trace`.
   - 0 → commune **non desservie** en livraison « home ».
   - Commune elle-même non résolue (adresse legacy sans `geo_town_id`) → idem (non
     desservie).
4. Une destination **non desservie / non résolue n'est pas bloquante en soi** :
   `by-cart` renvoie quand même le dernier tronçon **avec uniquement les options
   pickup** (§3.9), sans options « home ». Le checkout n'échoue (`422` « destination
   non desservie ») que si le client ne retient pas une option pickup et qu'aucune
   livraison home n'est donc déterminée.
5. Le front impose le **sélecteur commune/île** à la saisie d'adresse (Lot 1a) ; les
   adresses legacy sont migrées best-effort et signalées si non résolues.

---

## 7. Non-fonctionnel

1. **Performance**
   - Index déjà présents sur `from_place_id` / `to_place_id` / `from_partner_id`
     / `to_partner_id` ; ajouter index sur `Product.supplier_partner_id`,
     `Product.origin_place_id`, `Partner.default_origin_place_id`,
     `Address.geo_town_id`, `Place.geo_town_id`, `Place.geo_country_id`,
     `Place.is_delivery_destination`, `GeoTown.region_id`, `GeoRegion.country_id`.
   - `max_hops` borné (défaut 10) ; cache des routes par `to_place` pendant un
     appel ; nombre d'origines distinctes naturellement petit.
2. **Observabilité** — `trace` : origines résolues, routes candidates retenues /
   rejetées (avec raison), hubs de fusion détectés, scores de spécificité,
   `pricing_effective` par route. Logs structurés à chaque `by-cart` / `quote-cart`
   / checkout.
3. **Robustesse**
   - Fallback générique si aucune route override fournisseur.
   - Erreur explicite si destination non résolue, ou si une sous-expédition est
     `unroutable` **et** qu'aucune livraison n'est alors possible (checkout bloqué
     avec message clair) — sinon, livrer ce qui est routable et signaler le reste.
   - Sélection client invalide (route hors `options`) → `422`.
4. **Compatibilité — coupure nette (décidé)** : `CheckoutRequest.shipping_route_ids`
   est **supprimé** (remplacé par `shipping_selections`) ; les tests backend sont
   adaptés dans le Lot 4 ; l'adaptation `frontend` / `admin-frontend` au nouveau
   contrat est un chantier séparé (hors de ce cahier centré backend). Les anciens
   `ShippingRouteTracking` linéaires restent valides (le nouveau modèle est un
   sur-ensemble). Le référentiel géo (Lot 1a) migre les adresses existantes
   (best-effort) ; les non-résolues restent utilisables en pickup et sont signalées
   pour revue.
5. **Configuration** — réglages globaux (settings) :
   - `SHIPPING_PICKUP_ALWAYS_OFFERED: bool = true` — quand `true` (cas PF), toute
     route `mode = "pickup"` partant d'un hub final est ajoutée au dernier tronçon
     sans tenir compte de la zone desservie ni de la destination client ; quand
     `false`, le pickup n'est proposé que si la boutique dessert la zone du client
     (§3.9).
   - `SHIPPING_MAX_HOPS: int = 10` — profondeur max de la recherche de parcours.
   Les flags portés par les données (`is_default`, `is_customer_selectable`,
   `allow_consolidation`) restent prioritaires sur les défauts globaux pour les cas
   particuliers.

---

## 8. Stratégie d'implémentation (lots)

### Lot 1a — Référentiel géographique (prérequis)
- Tables `GeoCountry` / `GeoRegion` / `GeoTown` (+ CRUD, schémas, endpoints, écrans
  admin).
- Import des données : a minima PF (pays, archipels, communes, îles habitées) ;
  structure prête pour d'autres pays.
- Colonnes : `Address.geo_town_id`, `Place.geo_country_id`, `Place.geo_town_id`,
  `Place.is_delivery_destination` ; index associés.
- Migration des adresses existantes : match best-effort `(country, state, city)` →
  `GeoTown` ; non-résolues marquées pour revue (utilisables en pickup en attendant).
- (Sélecteur commune/île côté front à la saisie d'adresse — hors périmètre backend,
  chantier séparé.)

### Lot 1b — Données routage
- Migration Alembic : `Product.supplier_partner_id`, `Product.origin_place_id`,
  `Partner.default_origin_place_id`, `ShippingRoute.is_customer_selectable`,
  `ShippingRoute.is_default` ; index associés.
- Back-fill : créer/rattacher un `Partner` par `supplier_name` ; renseigner
  `Product.supplier_partner_id` et `Partner.default_origin_place_id` ; marquer une
  `is_default = true` par tronçon existant.

### Lot 2 — Moteur
- `RoutingEngine` : découpage en sous-expéditions, graphe par sous-expédition
  (réutilise `get_routes_between_places`), fusion forcée + détection des hubs,
  réduction en tronçons + `kind`, portée des overrides (§3.6), score de
  spécificité (§3.7), chiffrage via `calculate_shipping_for_routes` (§3.8),
  gestion `unroutable` / `rejected_candidates` / `trace`.
- Service de résolution de destination (§6).

### Lot 3 — API
- `POST /shipping/route/options/by-cart` (§4).
- `POST /shipping/route/quote-cart` (§5.2).
- Schémas Pydantic correspondants (réutiliser `ShippingPathQuoteResponse` /
  `ShippingSegmentCostResponse` pour les coûts).

### Lot 4 — Checkout + création du suivi (coupure nette)
- `CheckoutRequest` : **suppression** de `shipping_route_ids`, ajout de
  `shipping_selections` ; intégration `quote-cart` ; suppression de la logique
  `FulfillmentSegment` (§5.3) ; conservation de la réservation de stock.
- **Création du suivi au paiement** (remplace `_link_fulfillment_segments_to_tracking`
  / `_link_selected_routes_to_tracking`) : pour chaque sous-expédition, créer la
  chaîne de `ShippingRouteTracking` (un par tronçon, `sequence_order` 1..n) ; pour
  chaque tronçon mutualisé, créer (une fois par `(route_id, order_id)`) une
  `ShippingRouteTrackingConsolidation` partagée et y rattacher les trackings
  concernés (§2.5). Statut initial = statut `pending` du lifecycle (Lot 6, seed).
- **`DeliveryTask`** : créer une `DeliveryTask` (`delivery_type = home_delivery`,
  `address_id` = adresse client résolue) liée au dernier tronçon **si** l'option
  retenue est `home` ; **aucune** `DeliveryTask` si l'option est `pickup`
  (`requires_pickup`) — la destination « effective » est la boutique.
- `order.shipping_fee_amount` / `order.shipping_cost_breakdown` alimentés depuis le
  `ShippingCostSummary` ; réponse checkout : `applied_shipping_route_ids` = union des
  routes retenues.
- (L'adaptation du `frontend` / `admin-frontend` au nouveau contrat d'API est un
  chantier séparé, hors de ce cahier centré backend ; les tests backend qui
  postaient `shipping_route_ids` sont mis à jour ici.)

### Lot 5 — Tests
- Unitaires moteur : 1 fournisseur direct ; 2 fournisseurs même hub (fusion) ;
  2 fournisseurs + stock local (3 origines, fusion à 2 endroits = cas de
  référence §1) ; route override fournisseur sur tronçon amont (et override ignoré
  sur tronçon mutualisé) ; tronçon masqué (`is_customer_selectable = false`) ;
  dernier tronçon « last-mile » mêlant home + pickup ; pickup **toujours proposé**
  (`SHIPPING_PICKUP_ALWAYS_OFFERED = true`, commune résolue *et* non résolue) ;
  plusieurs boutiques pickup ; `include_pickup = false` ;
  `SHIPPING_PICKUP_ALWAYS_OFFERED = false` + zone desservie / non desservie ;
  sous-expédition `unroutable` ; commune non desservie → checkout bloqué sans pickup
  mais OK avec pickup retenu ; tarif hors fenêtre `effective_*`.
- Référentiel géo : résolution `Address.geo_town_id → Place` (0 / 1 / N) ; migration
  best-effort des adresses legacy.
- Intégration : `by-cart`, `quote-cart` (sélection valide / invalide / partielle).
- Non-régression checkout : devis, breakdown, chaînes `ShippingRouteTracking` +
  consolidations partagées créées, `DeliveryTask` créée si `home` / absente si
  `pickup` ; rejet d'un `shipping_route_ids` envoyé (champ supprimé).

### Lot 6 — Suivi des colis & opérations (backend)
Construit sur l'existant (`ShippingRouteTracking`, `ShippingRouteTrackingConsolidation`,
`ShippingRouteTrackingLogs`, `StatusDefinition` / `StatusTransition`, `DeliveryTask`)
— voir l'état actuel et les écarts en §12.

- **Seed du cycle de vie** : migration de données peuplant `StatusDefinition`
  (entité `route_tracking` : `pending` → `in_transit` → `arrived_hub` →
  `out_for_delivery` → `delivered` ; + états d'erreur `supplier_delay`,
  `segment_failed` ; entité `consolidation` : mêmes codes ; entité `delivery_task`)
  et `StatusTransition` (transitions autorisées, `auto_advance` sur l'enchaînement
  inter-tronçons, `requires_confirmation` où il faut). Le checkout cesse de créer
  des statuts à la volée.
- **Endpoint « board par tronçon »** : `GET /shipping/route/{route_id}/trackings`
  (filtres : statut, consolidé/non, plage de dates) renvoyant, pour ce tronçon, les
  trackings actifs avec leur commande, leur sous-expédition, leur consolidation
  éventuelle, le statut courant et l'ETA — la vue dont l'écran admin « colis en
  transit sur CDG→Papeete » a besoin. Variante `GET /shipping/route/legs/active`
  agrégée par tronçon (compteurs) pour la liste des tronçons en cours.
- **Consolidation en masse** :
  - `POST /shipping/consolidation` à partir d'**une liste de `tracking_id`** (même
    `route_id` requis) → crée la consolidation + rattache tous les trackings + met
    `total_orders` à jour ;
  - `POST /shipping/consolidation/{id}/trackings` / `DELETE
    /shipping/consolidation/{id}/trackings/{tracking_id}` (ajout/retrait) ;
  - `POST /shipping/consolidation/{id}/update-status` → applique le statut à la
    consolidation **et** en cascade à tous ses trackings (`update_trackings = true`),
    en journalisant `change_type = consolidation_override`.
- **Correctifs des bugs existants** :
  - `ShippingRouteTrackingConsolidationCrud.update_consolidation_status` écrit
    `status_code` (string) alors que le modèle a `status_id` (FK) → corriger pour
    résoudre le code vers un `StatusDefinition` de l'entité `consolidation` ;
  - `GET /shipping/tracking/{id}/status` : entité (`route_tracking`, pas
    `shipping_route_tracking`), résolution par `status_id` et non par code, champ
    `estimated_delivery` (et non `estimated_arrival`).
- **Auto-advance** : à chaque changement de statut d'une consolidation (ou d'un
  tracking de tronçon non mutualisé) vers un état marqué `auto_advance` sur la
  transition « fin de tronçon », activer automatiquement les trackings du tronçon
  `sequence_order + 1` de chaque sous-expédition concernée (réutilise
  `activate_next_route` / `get_next_route_for_order`), en journalisant
  `change_type = auto_advance`. Sinon, progression manuelle via
  `POST /shipping/tracking/{id}/update-status` et
  `POST /shipping/tracking/{id}/activate-next-route` (déjà présents).
- **`DeliveryTask`** : endpoints d'assignation (`assignee`), de planification
  (`scheduled_at`) et de changement de statut, et clôture qui marque le dernier
  tracking `delivered` ; pour une option `pickup`, gestion de l'« arrivé en
  boutique / remis au client » directement sur le tracking (pas de `DeliveryTask`).
- **Suivi client** : conserver `GET /shipping/tracking/order/{order_id}` (statut
  global dérivé + scénarios d'exception) — y vérifier la cohérence avec les chaînes
  multi-sous-expéditions (statut global = état du tronçon le moins avancé toutes
  sous-expéditions confondues).
- **Tests** : seed appliqué ; transitions valides/invalides ; consolidation depuis
  une liste de trackings ; `update-status` consolidation → cascade + logs ;
  auto-advance d'un tronçon au suivant ; board par tronçon ; `DeliveryTask`
  home vs pickup ; régression des deux bugs ci-dessus ; statut global de commande
  sur un parcours multi-sous-expéditions.

---

## 9. Critères d'acceptation

1. Un panier multi-fournisseurs produit **une sous-expédition par origine** et des
   **tronçons mutualisés** (cas §1 : Toulouse→CDG et Strasbourg→CDG distincts ;
   CDG→Papeete et Papeete→Arutua communs).
2. Un tronçon à une seule option (ou entièrement non sélectionnable) est
   **auto-sélectionné et masqué** ; le client ne voit que les `customer_choice`.
3. Une route générique `Toulouse→CDG` (`from_partner_id` null) est empruntée par
   tout fournisseur dont l'origine est *Toulouse*, sans duplication manuelle ; une
   route `from_partner_id = Fx` la **remplace pour Fx uniquement**, et seulement
   sur la partie amont privée de sa sous-expédition.
4. Le dernier tronçon est un **unique tronçon « last-mile »** (§3.5.1) dont les
   options mélangent livraisons home et retraits boutique ; le **retrait boutique
   est systématiquement proposé** quand `SHIPPING_PICKUP_ALWAYS_OFFERED = true`
   (même destination client non résolue, même île éloignée), et il n'exige **pas**
   d'adresse client ni de `DeliveryTask` quand il est retenu.
5. Le devis (`by-cart` par défaut, et `quote-cart` après sélection) est recalculé
   serveur, détaillé **par tronçon et par sous-expédition**, et réutilise le moteur
   de pricing existant (`ShippingCostSummary` / `route_metadata`).
6. Le checkout persiste les chaînes `ShippingRouteTracking` + consolidations
   partagées cohérentes avec les sélections ; l'ancienne logique
   `FulfillmentSegment` / heuristique d'adresse PF n'est plus utilisée ;
   `CheckoutRequest` n'accepte plus `shipping_route_ids` (rejet explicite).
7. Tout est explicable : `trace` (critères, hubs de fusion, override ignoré sur
   tronçon mutualisé) et `rejected_candidates` (raisons) sont renvoyés.
8. Le référentiel géo (`GeoCountry` / `GeoRegion` / `GeoTown`) est en place ; les
   adresses portent `geo_town_id` ; la destination « home » se résout via
   `Place.geo_town_id` + `Place.is_delivery_destination` ; une commune sans `Place`
   de livraison reste commandable en retrait boutique.

---

## 10. Risques et mitigations

| Risque | Mitigation |
|---|---|
| Produits non rattachés à un `Partner` / pas de Place d'origine | Lot 1b back-fill (`Partner` par `supplier_name`, `default_origin_place_id`) ; fallback `Inventory.place_id` ; ligne `unroutable` explicite sinon. |
| Lot 1a (référentiel géo) sous-estimé / qualité des données | Source officielle (ISPF / data.gouv) ; périmètre MVP = communes + îles habitées PF ; revue ; reste du monde ajouté à la demande. |
| Adresses legacy sans `geo_town_id` | Migration best-effort `(country, state, city)` → `GeoTown` ; non-résolues commandables en pickup et signalées pour revue. |
| Pas de scope géo sur les routes ⇒ un `Place` de livraison par commune desservie | Génération assistée des `Place` `is_delivery_destination` depuis les `GeoTown` ; routes « home » génériques depuis le hub Papeete vers chaque île desservie ; « route vers une zone » = évolution future (§11). |
| Cycles / hubs mal configurés | Recherche orientée avec `visited_places` + `max_hops` ; routes dirigées ; `trace` des chemins rejetés. |
| Explosion combinatoire | Évitée par construction (modèle tronçons : N tronçons × k options, pas kᴺ chemins) ; `max_hops` ; choix « consolidation maximale ». |
| Tarifs hétérogènes (devises, unités) | Réutilisation du pricing existant (`route_metadata` : `weight_unit`, `value_rate`, bornes, fenêtre `effective_*`) ; `pricing_effective` exposé. |
| Coupure nette du checkout (`shipping_route_ids` supprimé) | Lot 1a livré avant ; tests backend adaptés dans le Lot 4 ; adaptation `frontend` / `admin-frontend` = chantier séparé ; anciens `ShippingRouteTracking` linéaires restent valides. |
| Cycle de vie des statuts non figé / transitions absentes | Seed `StatusDefinition` + `StatusTransition` (Lot 6) ; le checkout cesse de créer des statuts à la volée ; transitions validées par `validate_status_transition`. |
| Création du suivi encore en mode « ancien » (`FulfillmentSegment`) | Réécriture autour des sous-expéditions + consolidations partagées (Lot 4, §2.5 / §5.3) ; couverte par les tests de non-régression checkout. |

---

## 11. Évolutions futures (hors MVP, prévues sans re-migration)

- **Fusion optionnelle** : flag `allow_split` / `force_consolidation` (sur hub ou
  route) déjà réservé conceptuellement via `allow_consolidation` ; permettre à une
  sous-expédition de garder un aval propre.
- **Parcours alternatifs exposés** : autoriser plus d'un parcours par
  sous-expédition quand une route le marque (au-delà du « converge le plus tôt »).
- **Routes vers une zone** : route `from_place → GeoRegion` (ex. « Papeete → tout
  l'archipel des Tuamotu à un tarif ») — réintroduirait une forme de scope ; à
  concevoir si un besoin de tarif « zone » apparaît (pas au MVP).
- **`Place.served_geo_town_ids`** sur les boutiques : restriction fine du retrait
  hors PF (quand `SHIPPING_PICKUP_ALWAYS_OFFERED = false`).
- **Préférences fines** : pondération coût/ETA/CO₂ paramétrable côté client.

---

## 12. Suivi des colis & opérations — état backend actuel & écarts (cadre du Lot 6)

> Section informative : ce qui est déjà codé côté backend pour le suivi
> post-paiement, et ce que le Lot 6 complète. (Le frontend admin n'existe pas
> encore — hors périmètre de ce cahier.)

### 12.1 Déjà en place (et couvert par des tests)

- **Modèles** : `ShippingRouteTracking` (commande → route → statut → adresse,
  `sequence_order` multi-hop, `consolidation_id`, `tracking_ref`,
  `estimated_delivery`), `ShippingRouteTrackingConsolidation` (groupe de trackings
  sur une même route, statut propre, `consolidation_code`, `total_orders`),
  `ShippingRouteTrackingLogs` (historique complet : `from`/`to`, `change_type` ∈
  `direct` / `consolidation_override` / `auto_advance` / `manual`, auteur, raison,
  transition), `StatusDefinition` / `StatusTransition` (catalogue de statuts par
  entité + transitions, `auto_advance`, `requires_confirmation`, `requires_scan`,
  `guard_name`), `DeliveryTask` (livraison finale home/pickup, `assignee`, statut,
  `scheduled_at`).
- **CRUD** (`ShippingRouteTrackingCrud`, `…ConsolidationCrud`, `…LogsCrud`) :
  `update_status` (validation de transition + log), `validate_status_transition`,
  `get_available_transitions`, `get_trackings_by_order_sequence`,
  `get_current_route_for_order`, `get_next_route_for_order`, `activate_next_route`
  (clôt l'étape + active la suivante), `get_unconsolidated_trackings`,
  `get_trackings_for_consolidation`, `add_tracking_to_consolidation`,
  `remove_tracking_from_consolidation`, `update_consolidation_status(update_trackings)`
  (cascade du statut sur tous les trackings du groupe), nombreuses requêtes sur les
  logs.
- **API** (`/api/v1/shipping/…`) : `GET /tracking/order/{order_id}` (suivi complet :
  tous les tronçons par séquence, consolidations, statut global dérivé, scénarios
  d'exception), `POST /tracking/{id}/update-status`, `GET /tracking/{id}/history`,
  `POST /tracking/{id}/activate-next-route`, CRUD auto sur `tracking`,
  `consolidation`, `status_definition`, `status_transition`, `delivery_task`,
  `logs/tracking/{id}`. Le checkout actuel crée déjà des `ShippingRouteTracking`
  (et une consolidation pour le segment « consolidation PF ») au paiement.

### 12.2 Écarts à combler (= Lot 6)

1. **Pas de seed du cycle de vie** : `StatusDefinition` / `StatusTransition` ne sont
   pas peuplés ; le checkout crée un `pending` à la volée. → seed (Lot 6).
2. **Pas d'endpoint « board par tronçon »** : il y a `get_by_route_id` et
   `get_consolidations_for_route`, mais rien qui agrège « tous les colis actifs sur
   CDG→Papeete avec leur commande, groupés ou non ». → endpoint (Lot 6).
3. **La mise à jour groupée n'est pas exposée en HTTP** :
   `update_consolidation_status(update_trackings=True)` existe au niveau CRUD mais
   sans endpoint ; et pas d'API « consolider une liste de trackings d'un coup »
   (seulement `add_tracking_to_consolidation` un par un). → endpoints (Lot 6).
4. **Bug** : `update_consolidation_status` écrit `status_code` (string) alors que le
   modèle `ShippingRouteTrackingConsolidation` a `status_id` (FK). → correctif (Lot 6).
5. **Bug** : `GET /tracking/{id}/status` utilise la mauvaise entité
   (`shipping_route_tracking`), passe un `status_id` là où un code est attendu, et lit
   `tracking.estimated_arrival` (inexistant ; champ = `estimated_delivery`). →
   correctif (Lot 6).
6. **Auto-advance non branché** : `StatusTransition.auto_advance` + `activate_next_route`
   existent mais aucun déclencheur n'enchaîne un tronçon au suivant. → branchement
   (Lot 6).
7. **`DeliveryTask` non créée au checkout** ni reliée au dernier tronçon ; pas
   d'endpoints d'assignation / planification / clôture. → création au checkout (Lot 4)
   + endpoints (Lot 6).
8. **Création du suivi encore en mode « ancien »** : pilotée par
   `_link_fulfillment_segments_to_tracking` / `_link_selected_routes_to_tracking`
   (heuristique `FulfillmentSegment`), pas par les sous-expéditions du nouveau
   moteur. → réécriture (Lot 4, §2.5 / §5.3).
