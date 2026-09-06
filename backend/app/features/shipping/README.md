# Shipping System

A comprehensive shipping and tracking system for e-commerce orders with support for multi-hop routes, consolidation, and final delivery.

## Overview

The shipping system tracks customer orders from supplier to final delivery address through multiple transportation routes. It supports consolidation of orders for efficient shipping and provides real-time status tracking with complete audit trails.

## Architecture Overview

### Features Structure

The shipping system integrates with other features in the application:
- **Place** (`app.features.place`): Physical locations (airports, ports, warehouses, customer addresses)  
- **Partner** (`app.features.partner`): Business actors (suppliers like Ingram Micro, shipping carriers)
- **Status** (`app.features.shipping.status`): Configurable status definitions and transitions
- **Shipping** (`app.features.shipping`): Route management and order tracking

### Core Models

1. **Place** (from `app.features.place`): Physical locations and addresses
2. **Partner** (from `app.features.partner`): Suppliers and carriers  
3. **StatusDefinition**: Configurable status catalog with workflow rules
4. **StatusTransition**: Allowed transitions with guards and automation
5. **ShippingRoute**: Defines available transportation routes between places
6. **ShippingRouteTracking**: Tracks customer choices and status for specific orders
7. **ShippingRouteTrackingConsolidation**: Groups multiple orders for batch processing
8. **ShippingRouteTrackingLogs**: Complete audit trail of all status changes
9. **DeliveryTask**: Manages individual delivery operations

## Core Concept: Bora Bora Customer Example

Let's follow a typical order from a customer on Bora Bora island:

### 1. Customer Order Flow

**Customer**: Lives on Bora Bora island  
**Order**: Places an order for electronics  
**Route Selection**: Customer chooses a shipping path:
1. **Air freight**: Ingram partner → Our warehouse (consolidated with other orders) - `sequence_order=1`
2. **Inter-island freight**: Our warehouse → Bora Bora address (Air Tahiti) - `sequence_order=2`

### 2. Multi-Hop Route Sequencing

Each `ShippingRouteTracking` has a `sequence_order` field to manage multi-step journeys:

- **sequence_order=1**: First route (Ingram → Warehouse)
- **sequence_order=2**: Second route (Warehouse → Bora Bora)
- **Auto-progression**: When route 1 completes → automatically activate route 2

This allows the system to know which route comes next and automatically progress the shipment.

### 3. System Models & Relationships

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│     Partner     │    │      Place      │    │ ShippingRoute   │
│   (Ingram)      │◄──►│   (Warehouse)   │◄──►│ (Air Route)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └─────────────┬─────────────────┬───────────────┘
                       ▼                 ▼
              ┌─────────────────┐ ┌─────────────────┐
              │ShippingRoute    │ │ShippingRoute    │
              │Tracking         │ │TrackingConsol.  │
              │(Order-centric)  │ │(Group status)   │
              └─────────────────┘ └─────────────────┘
                       │                 │
                       ▼                 ▼
              ┌─────────────────┐ ┌─────────────────┐
              │StatusDefinition │ │ShippingRoute    │
              │(Configurable)   │ │TrackingLogs     │
              │                 │ │(Audit trail)   │
              └─────────────────┘ └─────────────────┘
```

## Model Details

### Place
```python
# Bora Bora customer address
{
    "id": "bora-bora-address-uuid",
    "name": "Client Bora Bora",
    "type": "address",
    "city": "Bora Bora",
    "country": "PF",
}

# Our warehouse in Papeete
{
    "id": "papeete-warehouse-uuid",
    "name": "Entrepôt Papeete",
    "type": "warehouse",
    "city": "Papeete",
    "country": "PF",
}
```

### Partner
```python
# Ingram supplier partner
{"id": "ingram-uuid", "name": "Ingram Micro", "city": "Paris", "country": "FR"}

# Air Tahiti carrier
{"id": "air-tahiti-uuid", "name": "Air Tahiti", "city": "Papeete", "country": "PF"}
```

### StatusDefinition
```python
# Configurable status catalog
{
    "id": "status-pending-uuid",
    "entity": "route_tracking",
    "code": "pending",
    "name": "En attente",
    "sequence_order": 1,
    "ui_color": "orange",
    "ui_icon": "clock",
}

{
    "id": "status-dispatched-uuid",
    "entity": "route_tracking",
    "code": "dispatched",
    "name": "Expédié",
    "sequence_order": 2,
    "ui_color": "blue",
    "ui_icon": "truck",
}
```

### StatusTransition
```python
# Workflow rules with guards and automation
{
    "entity": "route_tracking",
    "from_code": "pending",
    "to_code": "dispatched",
    "guard_name": "has_consolidation",
    "auto_advance": False,
    "requires_confirmation": False,
}

{
    "entity": "route_tracking",
    "from_code": "dispatched",
    "to_code": "in_transit",
    "guard_name": null,
    "auto_advance": True,  # Automatic when flight departs
    "requires_confirmation": False,
}
```

### ShippingRoute
```python
# Route 1: Ingram → Warehouse
{
    "id": "route-1-uuid",
    "name": "Ingram to Warehouse",
    "from_place_id": "ingram-warehouse-uuid",
    "to_place_id": "papeete-warehouse-uuid",
    "from_partner_id": "ingram-uuid",
    "mode": "air",
    "operator": "Air France Cargo",
    "allow_consolidation": True,
}

# Route 2: Warehouse → Bora Bora
{
    "id": "route-2-uuid",
    "name": "Warehouse to Bora Bora",
    "from_place_id": "papeete-warehouse-uuid",
    "to_place_id": "bora-bora-address-uuid",
    "to_partner_id": "air-tahiti-uuid",
    "mode": "air",
    "operator": "Air Tahiti",
    "is_to_customer": True,
}
```

#### Tariff of a route

Every leg is priced by `calculate_shipping_for_routes`
(`services/pricing.py`), from the shipment's billable weight (max of actual
and volumetric weight) and declared value:

| Field | Meaning |
|---|---|
| `base_price` | Fixed part, billed once per shipment on this leg. |
| `price_per_kg` | Linear rate × billable weight (kg, or lb via `route_metadata.weight_unit`). |
| `weight_bands` | Classic carrier grid `[{"max_kg": 1, "price": 5}, {"max_kg": 3, "price": 8}, {"max_kg": null, "price": 12}]`. When set, it replaces `price_per_kg × weight`: the first band whose `max_kg` covers the weight prices it; a last band with `max_kg: null` covers everything heavier; without one, the excess above the last band is billed at `price_per_kg`. `base_price` still adds up. |
| `free_shipping_threshold` | Franco: the leg costs 0 once the declared value reaches this amount (wins over `route_metadata.min_total`). Only this leg is freed. |
| `route_metadata` | Extras: `value_percent` / `value_rate` (insurance-like % of value), `min_total` / `max_total`, `effective_from` / `effective_until` tariff window, `dim_factor_kg_per_m3` and `billing_basis` for volumetric weight. |

A one-warehouse shop with Colissimo and Chronopost needs two `is_to_customer`
routes (one `last_leg_delivery_type` each, e.g. `home_delivery` /
`express`), each with its own grid and franco; the customer picks one at
checkout and that route becomes the order's single tracked leg.

#### Origin of the goods (`services/origin.py`)

| Fact | Where | Effect |
|---|---|---|
| Main warehouse | `Place.is_main_warehouse` (one, `set_main_warehouse`) | Supplier goods converge there; last leg starts there. |
| Customs regime | `Place.customs_regime` on the supplier place, else country vs main warehouse, `customs_free_countries` setting | `DOMESTIC`: price = cost × margin × tax, no customs rate required, no declaration fee. `IMPORT`: CAF formula. `UNKNOWN`: import behaviour. |
| Dropshipping | `Place.dropship_enabled` | Checkout segment `SUPPLIER_DIRECT`: one supplier → customer leg (the supplier's customer route, else the chosen delivery mode). Otherwise `VIA_MAIN_WAREHOUSE`: supplier → main warehouse legs, then the shared last leg. |

### ShippingRouteTracking
```python
# Route 1 tracking with StatusDefinition relation
{
    "id": "tracking-1-uuid",
    "order_id": "order-123",
    "route_id": "route-1-uuid",
    "status_id": "status-pending-uuid",  # FK to StatusDefinition
    "sequence_order": 1,
    "selected_at": "2025-09-30T10:00:00Z",
    "consolidation_id": "consol-1-uuid",
}

# Route 2 tracking (waiting for route 1 completion)
{
    "id": "tracking-2-uuid",
    "order_id": "order-123",
    "route_id": "route-2-uuid",
    "status_id": "status-waiting-uuid",  # FK to StatusDefinition
    "sequence_order": 2,
    "selected_at": "2025-09-30T10:00:00Z",
}
```

### ShippingRouteTrackingConsolidation
```python
# Group multiple orders for Air France flight
{
    "id": "consol-1-uuid",
    "route_id": "route-1-uuid",
    "name": "AF Cargo Oct 1st",
    "consolidation_code": "AF-20250930-001",
    "status_id": "status-dispatched-uuid",  # FK to StatusDefinition
    "tracking_ref": "AF1234567",
    "total_orders": 15,
}
```

### ShippingRouteTrackingLogs
```python
# Complete audit trail with StatusDefinition relations
{
    "id": "log-1-uuid",
    "tracking_id": "tracking-1-uuid",
    "from_status_id": null,  # Initial status
    "to_status_id": "status-pending-uuid",  # FK to StatusDefinition
    "change_type": "manual",
    "changed_by": "customer",
    "reason": "Route selected by customer",
}

{
    "id": "log-2-uuid",
    "tracking_id": "tracking-1-uuid",
    "from_status_id": "status-pending-uuid",  # FK to StatusDefinition
    "to_status_id": "status-dispatched-uuid",  # FK to StatusDefinition
    "change_type": "consolidation_override",
    "consolidation_id": "consol-1-uuid",
    "changed_by": "system",
    "reason": "Status updated from consolidation: AF-20250930-001",
}
```

### DeliveryTask
```python
# Final delivery task to Bora Bora
{
    "id": "delivery-1-uuid",
    "order_id": "order-123",
    "address_place_id": "bora-bora-address-uuid",
    "delivery_type": "home_delivery",
    "assignee": "Air Tahiti Delivery",
    "status_code": "pending",
    "scheduled_at": "2025-10-02T14:00:00Z",
}
```

## Step-by-step Status Updates

#### 1. Order Placed & Route Selected
```python
# Customer selects routes with sequence and StatusDefinition
POST / api / shipping / tracking
[
    {
        "order_id": "order-123",
        "route_id": "route-1-uuid",  # Ingram → Warehouse
        "status_id": "status-pending-uuid",
        "sequence_order": 1,
        "selected_at": "2025-09-30T10:00:00Z",
    },
    {
        "order_id": "order-123",
        "route_id": "route-2-uuid",  # Warehouse → Bora Bora
        "status_id": "status-waiting-uuid",
        "sequence_order": 2,
        "selected_at": "2025-09-30T10:00:00Z",
    },
]

# Result: 2 ShippingRouteTracking entries created + audit logs
```

#### 2. Consolidation Created
```python
# Orders grouped for efficiency with StatusDefinition
POST / api / shipping / consolidations
{
    "route_id": "route-1-uuid",
    "name": "AF Cargo Oct 1st",
    "consolidation_code": "AF-20250930-001",
    "status_id": "status-pending-uuid",
}

# Add our order to consolidation
POST / api / shipping / consolidations / {consol_id} / add - tracking / {tracking_id}
```

#### 3. Consolidation Dispatched 
```python
# Update consolidation status → affects all orders
PUT / api / shipping / consolidations / {consol_id} / status
{"status_id": "status-dispatched-uuid", "tracking_ref": "AF1234567"}

# Result: All orders → "dispatched" + audit logs with consolidation_override
```

#### 4. In Transit to Warehouse
```python
PUT / api / shipping / consolidations / {consol_id} / status
{"status_id": "status-in-transit-uuid", "tracking_ref": "AF1234567"}

# Result: All orders → "in_transit" + automatic logs
```

#### 5. Arrival at Warehouse
```python
PUT / api / shipping / consolidations / {consol_id} / status
{"status_id": "status-arrived-uuid"}

# Auto-Route Progression: Route 1 completed → Activate Route 2
POST / api / shipping / tracking / {tracking - 1 - uuid} / activate - next

# System automatically:
# 1. Marks route 1 (Ingram → Warehouse) as "completed"
# 2. Finds next route (sequence_order = 2)
# 3. Activates route 2 (Warehouse → Bora Bora) with "in_progress"
# 4. Creates detailed audit logs for both changes
```

#### 6. Create Final Delivery Task
```python
POST / api / shipping / delivery - tasks
{
    "order_id": "order-123",
    "address_place_id": "bora-bora-address-uuid",
    "delivery_type": "home_delivery",
    "assignee": "Air Tahiti Delivery",
}
```

#### 7. Final Delivery
```python
PUT / api / shipping / delivery - tasks / {task_id} / status
{"status_code": "delivered"}
```

## Quick Start

### Required Imports

```python
# For API development
from app.features.place.models import Place
from app.features.partner.models import Partner
from app.features.shipping.models.status import StatusDefinition, StatusTransition
from app.features.shipping.models.shipping_route import ShippingRoute
from app.features.shipping.models.shipping_route_tracking import (
    ShippingRouteTracking,
    ShippingRouteTrackingConsolidation,
    ShippingRouteTrackingLogs,
)
from app.features.shipping.models.delivery_task import DeliveryTask
```

### Setup Order

1. Create Places (supplier warehouse, customer address)
2. Create Partners (Ingram, Air Tahiti)  
3. Create StatusDefinitions for workflow states
4. Create StatusTransitions for allowed workflows
5. Create ShippingRoutes between places
6. Customer selects route → ShippingRouteTracking with status_id
7. Optional consolidation → ShippingRouteTrackingConsolidation
8. All status changes → ShippingRouteTrackingLogs (audit trail)
9. Final delivery → DeliveryTask

## API Endpoints

### Route Selection
```bash
# Get available routes from supplier to customer
GET /api/shipping/routes/paths?from_place_id={supplier}&to_place_id={customer}

# Create tracking for selected routes with status relations
POST /api/shipping/tracking
```

### Multi-Route Sequencing
```bash
# Get all routes for an order in sequence  
GET /api/shipping/tracking/order/{order_id}/sequence

# Get current active route for order
GET /api/shipping/tracking/order/{order_id}/current

# Auto-activate next route in sequence
POST /api/shipping/tracking/{id}/activate-next

# Manual route progression
PUT /api/shipping/tracking/{id}/complete
```

### Status Management with StatusDefinition
```bash
# Update individual tracking with status_id
PUT /api/shipping/tracking/{id}/status
{
    "status_id": "status-uuid",
    "notes": "Status change reason"
}

# Update consolidation (affects all orders)
PUT /api/shipping/consolidations/{id}/status
{
    "status_id": "status-uuid"
}

# Get order status with full StatusDefinition data
GET /api/shipping/tracking/order/{order_id}

# Get complete status history (audit trail)
GET /api/shipping/tracking/{id}/logs
```

### Status Configuration
```bash
# Manage status definitions
GET /api/shipping/status-definitions?entity=route_tracking
POST /api/shipping/status-definitions
PUT /api/shipping/status-definitions/{id}

# Manage workflow transitions
GET /api/shipping/status-transitions?entity=route_tracking
POST /api/shipping/status-transitions
PUT /api/shipping/status-transitions/{id}
```

### Consolidation Management
```bash
# Create consolidation
POST /api/shipping/consolidations

# Add/remove orders
POST /api/shipping/consolidations/{id}/add-tracking/{tracking_id}
DELETE /api/shipping/consolidations/{id}/remove-tracking/{tracking_id}
```

## Multi-Route Sequencing Solution

### The Challenge
How does the system know to progress from **Ingram → Warehouse** to **Warehouse → Bora Bora**?

### The Solution: `sequence_order` Field

Each `ShippingRouteTracking` entry has a `sequence_order` field:

```python
# Order creation with route sequence
[
    {
        "order_id": "order-123",
        "route_id": "ingram-to-warehouse-route",
        "sequence_order": 1,  # First step
        "status_id": "status-pending-uuid",
    },
    {
        "order_id": "order-123",
        "route_id": "warehouse-to-borabora-route",
        "sequence_order": 2,  # Second step
        "status_id": "status-waiting-uuid",  # Waits for step 1
    },
]
```

### Auto-Progression Logic

When route 1 completes:
```python
# System automatically calls:
await crud_shipping_route_tracking.activate_next_route(
    session=session, order_id=order_id, current_tracking_id=route_1_tracking_id
)

# Result:
# 1. Route 1 → status "completed"
# 2. Route 2 → status "in_progress"
# 3. Complete audit trail in ShippingRouteTrackingLogs
# 4. Customer gets seamless progression
```

## Status System Integration

### StatusDefinition Relations

Instead of simple strings, the system now uses proper FK relations:

```python
# Old approach (string-based)
status_code: str = "pending"

# New approach (relation-based)
status_id: uuid.UUID = Field(foreign_key="status_definitions.id")
status: StatusDefinition = Relationship(...)

# Access rich metadata
tracking.status.name  # "En attente"
tracking.status.ui_color  # "orange"
tracking.status.sequence_order  # 1
```

### Complete Audit Trail

Every status change creates a log entry:

```python
# Automatic logging on every status update
{
    "tracking_id": "tracking-uuid",
    "from_status_id": "status-pending-uuid",  # FK relation
    "to_status_id": "status-dispatched-uuid",  # FK relation
    "change_type": "consolidation_override",  # Context
    "consolidation_id": "consol-uuid",  # Related consolidation
    "changed_by": "system",  # Who/what made change
    "was_auto_advance": False,  # Transition metadata
    "required_confirmation": False,  # Workflow metadata
}
```

### Workflow Configuration

StatusTransition defines allowed workflows:

```python
# Guard-protected transition
{
    "from_code": "pending",
    "to_code": "dispatched",
    "guard_name": "has_consolidation",  # Business rule
    "auto_advance": False,  # Manual trigger
    "requires_confirmation": False,  # No confirmation needed
}

# Automatic transition
{
    "from_code": "dispatched",
    "to_code": "in_transit",
    "auto_advance": True,  # Triggers automatically
    "requires_confirmation": False,  # No confirmation
}
```

## Key Features

- ✅ **Order-Centric Tracking**: Each order has dedicated tracking entries
- ✅ **Multi-Hop Routes**: Support complex route chains with `sequence_order`
- ✅ **Auto-Route Progression**: Automatic advancement from route to route
- ✅ **StatusDefinition Integration**: Type-safe status management with rich metadata
- ✅ **Complete Audit Trail**: ShippingRouteTrackingLogs tracks every change
- ✅ **Workflow Configuration**: StatusTransition with guards and automation
- ✅ **Consolidation Support**: Efficient grouping with status override
- ✅ **Real-time Updates**: Status propagation across related entities
- ✅ **Flexible Delivery**: Multiple final delivery options
- ✅ **Partner Integration**: Support for various suppliers and carriers
- ✅ **Geographic Flexibility**: Works with any location/address setup

This system efficiently handles the complexity of multi-island shipping while providing clear tracking, configurable workflows, and complete audit trails for customers and operations teams.
