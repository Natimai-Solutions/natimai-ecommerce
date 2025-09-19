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

## 🔧 Core Components

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
    event_type="user.created",
    payload={"user_id": 123, "email": "user@example.com"}
)

# Get handlers for an event type
handlers = outbox_registry.get_handlers("user.created")
```

**Key Features:**
- Handler registration and discovery
- Event publishing interface
- Multi-handler support per event type
- Model class association
- Registry introspection methods

### 3. **decorators.py** - Handler Registration
Decorators for automatic handler registration during application startup.

```python
from app.outbox.decorators import outbox_handler

@outbox_handler("user.created", User)
async def handle_user_created(event_data: dict, context: dict = None):
    """Send welcome email when user is created."""
    logger.info(f"Processing user creation: {event_data}")
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

@outbox_handler("user.created", User)
async def send_welcome_email(event_data: dict):
    """Send welcome email to new users."""
    user_email = event_data["email"]
    await email_service.send_welcome_email(user_email)

@outbox_handler("user.created", User)
async def create_user_profile(event_data: dict):
    """Create default user profile."""
    user_id = event_data["user_id"]
    await profile_service.create_default_profile(user_id)
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
    logger.info(f"Processing user {user_id} with email {email}")
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
        logger.info(f"Assigned account manager to premium user {event_data['user_id']}")
    else:
        await send_standard_welcome(event_data["user_id"])
        logger.info(f"Sent standard welcome to user {event_data['user_id']}")
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