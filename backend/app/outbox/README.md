# Outbox Pattern Implementation

## Overview

This module implements the **Outbox Pattern** for reliable event-driven architecture in FastAPI applications. The Outbox Pattern ensures data consistency between your application and external systems by storing events in the same database transaction as your business data, then processing them asynchronously.

## 📁 Directory Structure

```
app/outbox/
├── __init__.py           # Module initialization
├── models.py             # OutboxEvent database model
├── registry.py           # Event handler registry and management
├── decorators.py         # Handler registration decorators
├── loader.py             # Auto-discovery and loading of handlers
├── poller.py             # Event processing and ARQ integration
└── README.md             # This documentation
```

## � Event Naming Convention

This outbox pattern follows a simple and consistent naming convention for event types:

**Format:** `{action}.{model_name}`

**Examples:**
- `create.user` - When a new user is created
- `update.user` - When user data is updated  
- `delete.user` - When a user is deleted
- `create.payment` - When a payment is processed
- `update.order` - When an order status changes
- `delete.product` - When a product is removed

**Benefits:**
- **Intuitive**: Easy to understand what the event represents
- **Consistent**: All events follow the same pattern
- **Filterable**: Easy to filter events by action (`create.*`) or model (`*.user`)
- **Debuggable**: Clear event names in logs and monitoring

**CRUD Integration:**
When using the base CRUD class with outbox integration, configure events like this:

```python
crud_payment = PaymentCrud(
    model=Payment,
    outbox_events={
        "after_create": "create.payment",
        "after_update": "update.payment", 
        "after_delete": "delete.payment"
    }
)
```

## �🔧 Core Components

### 1. **models.py** - Database Model
Defines the `OutboxEvent` table that stores all pending events.

```python
class OutboxEvent(SQLModel, table=True):
    id: UUID                    # Unique event identifier
    type: str                   # Event type (e.g., "user.created")
    payload: Dict[str, Any]     # Event data as JSON
    status: OutboxStatus        # PENDING/RUNNING/DONE/FAILED
    attempts: int               # Retry counter
    next_run_at: datetime       # When to process next
    last_error: str             # Error from last failed attempt
    created_at: datetime        # Event creation timestamp
    updated_at: datetime        # Last modification timestamp
```

**Key Features:**
- Event persistence with full audit trail
- Retry mechanism with exponential backoff
- Status tracking for monitoring
- Indexed fields for efficient querying

### 2. **registry.py** - Handler Management
Central registry for managing event handlers and publishing events.

```python
from app.outbox.registry import outbox_registry

# Publish an event
await outbox_registry.publish(
    session=db_session,
    event_type="create.user",
    payload={
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "model": "User",
        "action": "create",
        "user_id": "456e4567-e89b-12d3-a456-426614174000",
        "timestamp": "2025-09-18T14:30:00.123456",
        "data": {"name": "John Doe", "email": "john@example.com"}
    }
)

# Get handlers for an event type
handlers = outbox_registry.get_handlers("create.user")
```

**Standardized Payload Structure:**
All outbox events follow a consistent payload structure:

```python
{
    "id": str,           # ID of the affected record
    "model": str,        # Model class name (e.g., "User", "Payment")
    "action": str,       # Operation type ("create", "update", "delete")  
    "user_id": str,      # ID of user performing the operation (nullable)
    "timestamp": str,    # ISO timestamp of the operation
    "data": dict         # Operation-specific data
}
```

**Data Field Contents:**
- **Create/Update**: Contains the data being created/modified
- **Delete**: Contains minimal safe data (just ID) to avoid serialization issues

**Key Features:**
- Handler registration and discovery
- Event publishing interface
- Multi-handler support per event type
- Model class association
- Registry introspection methods
- Standardized payload structure
- Safe serialization for all operations

### 3. **decorators.py** - Handler Registration
Decorators for automatic handler registration during application startup.

```python
from app.outbox.decorators import outbox_handler

@outbox_handler("user.created", User)
async def handle_user_created(event_data: dict, context: dict = None):
    """Send welcome email when user is created."""
    logger.debug(f"Processing user creation: {event_data}")
    await send_welcome_email(event_data["email"])
```

**Available Decorators:**
- `@outbox_handler(event_type, model_class)` - Single event handler
- `@bulk_outbox_handler(event_types, model_class)` - Multi-event handler

**Features:**
- Automatic handler registration
- Error handling and logging wrapper
- Type validation and safety
- Development-time validation

### 4. **loader.py** - Auto-Discovery
Automatically discovers and loads handlers from the `/app/handlers` directory.

```python
from app.outbox.loader import load_handlers

# Load all handlers from /app/handlers directory
load_handlers()

# Development: reload handlers without restart
reload_handlers()
```

**Features:**
- Automatic module discovery
- Error handling for failed imports
- Development reload capabilities
- Comprehensive logging

### 5. **poller.py** - Event Processing
Processes pending events by dispatching them to ARQ workers.

```python
from app.outbox.poller import OutboxPoller

poller = OutboxPoller()

# Process all pending events
await poller.process_pending_events(session)

# Retry failed events
await poller.retry_failed_events(session, max_attempts=5)

# Cleanup old processed events
await poller.cleanup_old_events(session, days=7)
```

**Features:**
- ARQ integration for async processing
- Exponential backoff retry logic
- Batch processing capabilities
- Event lifecycle management
- Comprehensive error handling

## 🚀 Quick Start

### 1. Create Event Handlers

Create handlers in the `/app/handlers` directory:

```python
# app/handlers/user_handlers.py
from app.outbox.decorators import outbox_handler
from app.models.user import User

@outbox_handler("create.user", User)
async def send_welcome_email(event_data: dict):
    """Send welcome email to new users."""
    user_email = event_data["email"]
    await email_service.send_welcome_email(user_email)

@outbox_handler("create.user", User)
async def create_user_profile(event_data: dict):
    """Create default user profile."""
    user_id = event_data["user_id"]
    await profile_service.create_default_profile(user_id)

@outbox_handler("create.payment", Payment)
async def process_payment_notification(event_data: dict):
    """Send payment confirmation."""
    await payment_service.send_confirmation(event_data["payment_id"])

@outbox_handler("update.order", Order)
async def track_order_status(event_data: dict):
    """Update order tracking."""
    if event_data["status"] == "shipped":
        await tracking_service.notify_customer(event_data["order_id"])
```

### 2. Publish Events in Your CRUD

```python
# In your CrudBase or specific CRUD classes
from app.outbox.registry import outbox_registry

async def after_create_commit(self, session, *, record, data, user):
    # Call parent method
    await super().after_create_commit(session, record=record, data=data, user=user)
    
    # Publish outbox event
    await outbox_registry.publish(
        session=session,
        event_type="user.created",
        payload={
            "user_id": str(record.id),
            "email": record.email,
            "created_by": str(user.id) if user else None
        }
    )
```

### 3. Start the Services

```bash
# Start the API
./entrypoint.sh api

# Start the ARQ worker
./entrypoint.sh worker

# Start the outbox poller
./entrypoint.sh poller
```

## 🔄 Event Flow

```mermaid
sequenceDiagram
    participant API as FastAPI API
    participant DB as Database
    participant Poller as Outbox Poller
    participant ARQ as ARQ Worker
    participant Handler as Event Handler
    
    API->>DB: 1. Save business data + outbox event (same transaction)
    Poller->>DB: 2. Poll for pending events
    Poller->>ARQ: 3. Enqueue handler jobs
    ARQ->>Handler: 4. Execute event handlers
    Handler-->>ARQ: 5. Complete/fail
    ARQ-->>Poller: 6. Update event status
    Poller->>DB: 7. Mark event as DONE/FAILED
```

## 📊 Event Lifecycle

1. **PENDING** - Event created, waiting to be processed
2. **RUNNING** - Event being processed by poller
3. **DONE** - All handlers executed successfully
4. **FAILED** - Processing failed after max retries

## 🔄 Retry Strategy & Error Handling

### **Architecture: Separation of Responsibilities**

The outbox pattern implements a **two-level retry strategy** with clear separation of concerns:

#### **Level 1: Outbox Event Orchestration**
- **Responsibility**: Ensure events reach ARQ successfully
- **Retry Scope**: Entire event (all handlers together)
- **Trigger**: Failed to enqueue handlers to ARQ
- **Backoff**: Exponential (10s, 30s, 1m, 5m, 15m)

#### **Level 2: ARQ Handler Execution**  
- **Responsibility**: Execute individual handlers reliably
- **Retry Scope**: Individual handler only
- **Trigger**: Handler function fails during execution
- **Backoff**: ARQ's built-in retry (configurable)

### **Idempotence & Deduplication**

**Key Design Decision**: Each handler job uses a **fixed job ID** for deduplication:

```python
job_id = f"outbox:{event.id}:{handler.__name__}"
# Example: "outbox:123e4567-e89b-12d3-a456-426614174000:send_email_notification"
```

#### **Why Fixed Job IDs?**
1. **Idempotence**: Successfully executed handlers won't re-run if event is replayed
2. **Consistency**: Same event always produces same job IDs
3. **Observability**: Predictable job IDs for debugging

#### **Behavior with Retries**
- ✅ **Handler succeeds**: Job marked successful, won't re-run on event replay
- ❌ **Handler fails**: ARQ retries the individual handler (up to `max_tries`)
- 🔄 **Event retried**: Only failed/pending handlers are re-enqueued
- 🎯 **Partial failures**: Successful handlers remain completed

### **Example Scenario**

```
Event: "user.created" with 3 handlers
├── send_welcome_email     ✅ Succeeds first try
├── create_user_profile    ❌ Fails (network timeout)
└── update_analytics       ✅ Succeeds second try

Result after event retry:
├── send_welcome_email     ⏭️  Skipped (already successful)
├── create_user_profile    🔄 Re-executed by ARQ retry
└── update_analytics       ⏭️  Skipped (already successful)
```

### **ARQ Worker Configuration**

```python
# app/core/arq_worker.py
class WorkerSettings:
    functions = [your_handlers]
    
    # Individual handler retry settings
    max_tries = 3          # 3 attempts per handler
    retry_delay = 10       # 10s between ARQ retries
    job_timeout = 300      # 5min timeout per handler
    keep_result = 3600     # Keep results 1h for debugging
```

### **When Handlers Fail**

#### **During ARQ Enqueue (Level 1)**
```python
# In poller.py - if enqueue fails
except Exception as e:
    event.status = "PENDING"  # Event will retry
    event.attempts += 1
    event.next_run_at = now + exponential_backoff
    # All handlers will be re-enqueued
```

#### **During Handler Execution (Level 2)**
```python
# Handled by ARQ automatically
@outbox_handler("user.created", User)
async def send_email(event_data: dict):
    if random.random() < 0.3:  # 30% failure rate
        raise Exception("SMTP timeout")  # ARQ will retry this handler
    # Success - job marked complete with fixed job_id
```

### **Monitoring & Observability**

#### **Event Level** (Database)
```sql
-- Events by status
SELECT status, COUNT(*) FROM outbox_event GROUP BY status;

-- Failed events with errors
SELECT id, type, attempts, last_error 
FROM outbox_event 
WHERE status = 'FAILED';

-- Events with high retry counts
SELECT id, type, attempts, last_error 
FROM outbox_event 
WHERE attempts > 2;
```

#### **Handler Level** (ARQ/Redis)
```python
# Check ARQ job status
from arq import create_pool
pool = await create_pool(redis_settings)
job = await pool.get_job("outbox:123:send_email")
print(f"Status: {job.status}, Result: {job.result}")
```

## 🎯 Benefits

### **Guaranteed Delivery**
Events are stored in the same database transaction as your business data, ensuring they're never lost.

### **At-Least-Once Processing**
Events will be processed at least once, with retry logic for failed attempts.

### **Decoupled Architecture**
Event publishers don't need to know about handlers, enabling clean separation of concerns.

### **Scalability**
Multiple handlers can process the same event type, and multiple poller instances can run in parallel.

### **Observability**
Full audit trail of events, attempts, and errors for monitoring and debugging.

## 🔧 Configuration

### Environment Variables

```bash
# Database connection
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/db

# Redis for ARQ
REDIS_URL=redis://localhost:6379

# Outbox polling interval (seconds)
OUTBOX_POLL_INTERVAL=5

# Max retry attempts
OUTBOX_MAX_ATTEMPTS=5
```

### Docker Services

```yaml
# docker-compose.yml
services:
  outbox-poller:
    build: .
    command: ["./entrypoint.sh", "poller"]
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
    restart: unless-stopped
```

## 🐛 Troubleshooting

### **Handlers not executing**
1. Check if handlers are properly registered: `outbox_registry.list_event_types()`
2. Verify the poller is running and processing events
3. Check ARQ worker logs for execution errors

### **Events stuck in RUNNING state**
- Usually indicates ARQ worker failure or timeout
- Use `retry_failed_events()` to reset stuck events

### **High retry counts**
- Check handler implementation for bugs
- Verify external service availability
- Consider implementing circuit breaker pattern

## 📝 Best Practices

### **Handler Implementation**
- Keep handlers idempotent (safe to run multiple times)
- Handle external service failures gracefully
- Use structured logging for observability
- Validate event data at handler entry

### **Event Design**
- Include all necessary data in the payload
- Use clear, hierarchical event type naming (`domain.action`)
- Version your event schemas for backward compatibility
- Keep payloads reasonably small

### **Monitoring**
- Monitor event processing latency
- Alert on high failure rates
- Track event volume and patterns
- Implement dashboards for outbox health

## 🔍 Monitoring & Observability

The outbox system provides comprehensive logging and can be monitored through:

- **Event status distribution** (PENDING/RUNNING/DONE/FAILED)
- **Processing latency** and throughput
- **Retry patterns** and failure analysis
- **Handler execution** times and success rates

All components use structured logging with correlation IDs for request tracing across the event processing pipeline.

## 🚀 Advanced Usage

### Custom Handler Arguments

Handlers receive the event payload as keyword arguments:

```python
@outbox_handler("user.created")
async def handle_user_created(user_id: str, email: str, **kwargs):
    """Handler receives payload fields as arguments."""
    logger.debug(f"Processing user {user_id} with email {email}")
```

### Conditional Processing

You can implement conditional logic directly within your handlers:

```python
@outbox_handler("user.created")
async def handle_user_created(event_data: dict):
    """Process user creation with conditional logic."""
    # Check if user is premium
    if event_data.get("subscription_tier") == "premium":
        await assign_account_manager(event_data["user_id"])
        logger.debug(f"Assigned account manager to premium user {event_data['user_id']}")
    else:
        await send_standard_welcome(event_data["user_id"])
        logger.debug(f"Sent standard welcome to user {event_data['user_id']}")
```

### Bulk Operations

Handle multiple related event types with one handler:

```python
@bulk_outbox_handler(["user.created", "user.updated", "user.reactivated"])
async def sync_user_to_crm(event_data: dict):
    """Sync any user change to CRM system."""
    await crm_service.sync_user(event_data)
```

### Error Handling

Implement custom error handling within handlers:

```python
@outbox_handler("payment.processed")
async def process_payment(payment_id: str, amount: float, **kwargs):
    try:
        await payment_service.process(payment_id, amount)
    except PaymentServiceError as e:
        if e.is_retryable():
            logger.warning(f"Retryable payment error: {e}")
            raise  # Let ARQ retry
        else:
            logger.error(f"Permanent payment error: {e}")
            await send_payment_failure_notification(payment_id)
            # Don't raise - mark as handled
```

## 🧪 Testing

### Unit Testing Handlers

```python
import pytest
from app.handlers.user_handlers import send_welcome_email

@pytest.mark.asyncio
async def test_send_welcome_email():
    event_data = {"user_id": "123", "email": "test@example.com"}
    
    # Mock external services
    with patch("app.services.email_service.send_welcome_email") as mock_email:
        await send_welcome_email(event_data)
        mock_email.assert_called_once_with("test@example.com")
```

### Integration Testing

```python
@pytest.mark.asyncio
async def test_outbox_event_processing(db_session):
    # Publish event
    event = await outbox_registry.publish(
        session=db_session,
        event_type="user.created",
        payload={"user_id": "123", "email": "test@example.com"}
    )
    
    # Process event
    poller = OutboxPoller()
    processed = await poller.process_pending_events(db_session)
    
    assert processed == 1
    
    # Verify event status
    await db_session.refresh(event)
    assert event.status == OutboxStatus.DONE
```

This comprehensive outbox implementation provides a robust foundation for event-driven architecture in your FastAPI e-commerce application.