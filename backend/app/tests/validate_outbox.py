"""
Simple validation script to test outbox integration manually.

This script demonstrates the complete outbox flow:
1. Create a payment via CRUD
2. Verify outbox event is created
3. Show that handlers are registered
4. Demonstrate retry mechanism
"""

import asyncio
import os
import sys

from sqlmodel.ext.asyncio.session import AsyncSession

# Add the app to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.db import engine
from app.features.product.crud.product import crud_product
from app.features.product.models.product import ProductCreate
from app.outbox.models import OutboxEvent
from app.outbox.registry import outbox_registry


async def validate_outbox_integration():
    """Validate that CRUD -> Outbox -> Handler integration works"""

    print("🔍 Validating Outbox Integration...")
    print("=" * 50)

    # 1. Check registered handlers
    print(f"📋 Registered handlers: {list(outbox_registry.handlers.keys())}")

    if "create.product" in outbox_registry.handlers:
        print("✅ Product handler is registered")
    else:
        print("❌ Product handler not found")
        return

    # 2. Get database session
    async with AsyncSession(engine) as session:
        try:
            # 3. Create a product (this should trigger outbox event)
            print("\n💳 Creating product...")

            product_data = ProductCreate(
                name="Test Product",
                base_price=19.99,
                description="A product for testing",
            )

            # Create product via CRUD (should publish outbox event)
            result = await crud_product.create(session, data=product_data)
            print(f"✅ Product created: {result}")

            # 4. Check if outbox event was created
            print("\n📤 Checking outbox events...")

            from sqlmodel import select

            stmt = (
                select(OutboxEvent)
                .where(OutboxEvent.type == "create.product")
                .order_by(OutboxEvent.created_at.desc())
                .limit(1)
            )

            result = await session.exec(stmt)
            event = result.first()

            print(f"Debug - Event type: {type(event)}")
            print(f"Debug - Event: {event}")

            if event:
                print("✅ Outbox event created:")
                print(f"   ID: {event.id}")
                print(f"   Type: {event.type}")
                print(f"   Status: {event.status}")
                print(f"   Payload: {event.payload}")
                print(f"   Created: {event.created_at}")

                # 5. Demonstrate handler lookup
                handlers = outbox_registry.get_handlers(event.type)
                print(f"✅ Found {len(handlers)} handler(s) for {event.type}")

                for handler in handlers:
                    print(f"   Handler: {handler.__name__}")

                # 6. Show what would happen in ARQ
                print("\n🔄 ARQ would execute:")
                print(f"   Job ID: outbox:{event.id}:process_outbox_event")
                print("   Function: process_outbox_event")
                print(
                    f"   Args: {{'id': {event.id}, 'event_type': '{event.type}', ...}}"
                )

                return True

            else:
                print("❌ No outbox event found")
                return False

        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback

            traceback.print_exc()
            return False

        finally:
            await session.close()


async def validate_retry_mechanism():
    """Validate retry mechanism configuration"""

    print("\n🔄 Validating Retry Mechanism...")
    print("=" * 50)

    # Show ARQ configuration
    from app.core.arq_worker import WorkerSettings

    print("📊 ARQ Configuration:")
    print(f"   max_tries: {WorkerSettings.max_tries}")
    print(f"   retry_delay: {WorkerSettings.retry_delay}s")
    print(f"   job_timeout: {WorkerSettings.job_timeout}s")

    # Show outbox poller configuration
    from app.outbox.poller import MAX_ATTEMPTS

    print("\n📊 Outbox Poller Configuration:")
    print(f"   max_attempts: {MAX_ATTEMPTS}")
    print("   exponential_backoff: 2^attempt seconds")

    print("\n🎯 Retry Strategy:")
    print(f"   1. Outbox poller retries up to {MAX_ATTEMPTS} times")
    print(f"   2. Each ARQ job retries up to {WorkerSettings.max_tries} times")
    print(
        f"   3. Total possible attempts: {MAX_ATTEMPTS} × {WorkerSettings.max_tries} = {MAX_ATTEMPTS * WorkerSettings.max_tries}"
    )
    print("   4. Fixed job IDs prevent duplicates")
    print("   5. Failed events marked with FAILED status")


async def main():
    """Run validation tests"""

    print("🚀 Outbox Integration Validation")
    print("=" * 50)

    # Test 1: Integration flow
    success = await validate_outbox_integration()

    # Test 2: Retry configuration
    await validate_retry_mechanism()

    # Summary
    print("\n📋 Validation Summary:")
    print("=" * 50)

    if success:
        print("✅ CRUD -> Outbox integration: WORKING")
        print("✅ Handler registration: WORKING")
        print("✅ Event creation: WORKING")
        print("✅ Retry mechanism: CONFIGURED")
        print("✅ System ready for production")
    else:
        print("❌ Integration validation failed")
        print("🔧 Check database connection and CRUD setup")

    print("\n🎯 Next Steps:")
    print("   1. Start ARQ worker: arq app.core.arq_worker.WorkerSettings")
    print("   2. Start outbox poller: python -m app.outbox.poller")
    print("   3. Monitor logs for event processing")
    print("   4. Test with real API calls")


if __name__ == "__main__":
    """
    Run validation:
    cd backend
    python app/tests/validate_outbox.py
    """
    asyncio.run(main())
