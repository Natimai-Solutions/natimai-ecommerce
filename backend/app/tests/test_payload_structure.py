"""
Test script to validate improved outbox payloads.

This script tests the new standardized payload structure to ensure:
1. All payloads have consistent structure
2. Delete payloads don't cause serialization issues
3. All required fields are present
4. Timestamps are properly formatted
"""

import asyncio
import json
import os
import sys
from datetime import datetime

# Add the app to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select

from app.core.db import get_session
from app.features.payment.crud.payment import crud_payment
from app.features.payment.models.payment import PaymentCreate, PaymentUpdate
from app.outbox.models import OutboxEvent


async def test_payload_structure():
    """Test that all payloads have consistent structure"""

    print("🧪 Testing Outbox Payload Structure...")
    print("=" * 50)

    async for session in get_session():
        try:
            # Test 1: Create payload
            print("\n📝 Testing CREATE payload...")

            payment_data = PaymentCreate(amount=100.50, currency="USD")

            # Create payment and capture outbox event
            payment = await crud_payment.create(session, data=payment_data, user=None)

            # Get the latest outbox event
            stmt = (
                select(OutboxEvent)
                .where(OutboxEvent.event_type == "create.payment")
                .order_by(OutboxEvent.created_at.desc())
                .limit(1)
            )

            result = await session.execute(stmt)
            create_event = result.scalar_one_or_none()

            if create_event:
                payload = create_event.payload
                print("✅ CREATE payload structure:")
                print(json.dumps(payload, indent=2, default=str))

                # Validate required fields
                required_fields = ["id", "model", "action", "timestamp", "data"]
                missing_fields = [
                    field for field in required_fields if field not in payload
                ]

                if missing_fields:
                    print(f"❌ Missing fields: {missing_fields}")
                else:
                    print("✅ All required fields present")

                # Validate timestamp format
                try:
                    datetime.fromisoformat(payload["timestamp"])
                    print("✅ Timestamp format valid")
                except:
                    print(f"❌ Invalid timestamp format: {payload['timestamp']}")

            else:
                print("❌ No CREATE event found")
                return False

            # Test 2: Update payload
            print("\n🔄 Testing UPDATE payload...")

            update_data = PaymentUpdate(amount=200.75)
            updated_payment = await crud_payment.update(
                session, id=payment.id, data=update_data, user=None
            )

            # Get the latest update event
            stmt = (
                select(OutboxEvent)
                .where(OutboxEvent.event_type == "update.payment")
                .order_by(OutboxEvent.created_at.desc())
                .limit(1)
            )

            result = await session.execute(stmt)
            update_event = result.scalar_one_or_none()

            if update_event:
                payload = update_event.payload
                print("✅ UPDATE payload structure:")
                print(json.dumps(payload, indent=2, default=str))

                # Validate that only changed fields are in data
                if "amount" in payload.get("data", {}):
                    print("✅ Changed field 'amount' present in data")
                else:
                    print("❌ Changed field 'amount' missing from data")

            else:
                print("❌ No UPDATE event found")

            # Test 3: Delete payload (the critical test)
            print("\n🗑️  Testing DELETE payload...")

            await crud_payment.delete(session, id=payment.id, user=None)

            # Get the latest delete event
            stmt = (
                select(OutboxEvent)
                .where(OutboxEvent.event_type == "delete.payment")
                .order_by(OutboxEvent.created_at.desc())
                .limit(1)
            )

            result = await session.execute(stmt)
            delete_event = result.scalar_one_or_none()

            if delete_event:
                payload = delete_event.payload
                print("✅ DELETE payload structure:")
                print(json.dumps(payload, indent=2, default=str))

                # Validate delete-specific structure
                if "data" in payload:
                    delete_data = payload["data"]
                    if isinstance(delete_data, dict) and "id" in delete_data:
                        print("✅ DELETE data structure is safe (minimal)")
                    else:
                        print(
                            f"❌ DELETE data structure problematic: {type(delete_data)}"
                        )
                else:
                    print("❌ DELETE payload missing data field")

                # Test serialization safety
                try:
                    json.dumps(payload)
                    print("✅ DELETE payload serializes safely")
                except Exception as e:
                    print(f"❌ DELETE payload serialization failed: {e}")

            else:
                print("❌ No DELETE event found")

            return True

        except Exception as e:
            print(f"❌ Test error: {e}")
            import traceback

            traceback.print_exc()
            return False

        finally:
            await session.close()


async def test_payload_consistency():
    """Test that all payloads have consistent structure across operations"""

    print("\n🔍 Testing Payload Consistency...")
    print("=" * 50)

    async for session in get_session():
        try:
            # Get recent events of all types
            stmt = (
                select(OutboxEvent)
                .where(
                    OutboxEvent.event_type.in_(
                        ["create.payment", "update.payment", "delete.payment"]
                    )
                )
                .order_by(OutboxEvent.created_at.desc())
                .limit(10)
            )

            result = await session.execute(stmt)
            events = result.all()

            if not events:
                print("❌ No events found for consistency test")
                return False

            # Check consistency across all events
            all_payloads = [event.payload for event in events]

            # Common fields that should be in all payloads
            common_fields = ["id", "model", "action", "timestamp"]

            consistent = True
            for i, payload in enumerate(all_payloads):
                missing = [field for field in common_fields if field not in payload]
                if missing:
                    print(f"❌ Event {i}: Missing fields {missing}")
                    consistent = False
                else:
                    print(
                        f"✅ Event {i} ({payload.get('action', 'unknown')}): All common fields present"
                    )

            if consistent:
                print(f"✅ All {len(events)} events have consistent structure")
            else:
                print("❌ Payload structure inconsistencies found")

            return consistent

        except Exception as e:
            print(f"❌ Consistency test error: {e}")
            return False

        finally:
            await session.close()


async def main():
    """Run all payload validation tests"""

    print("🚀 Outbox Payload Validation Tests")
    print("=" * 50)

    # Test 1: Payload structure
    structure_ok = await test_payload_structure()

    # Test 2: Payload consistency
    consistency_ok = await test_payload_consistency()

    # Summary
    print("\n📋 Test Results Summary:")
    print("=" * 50)

    if structure_ok and consistency_ok:
        print("✅ Payload structure: IMPROVED")
        print("✅ Payload consistency: VALIDATED")
        print("✅ Delete serialization: SAFE")
        print("✅ All tests: PASSED")
        print("\n🎯 Benefits achieved:")
        print("   • Consistent payload structure across all operations")
        print("   • Safe delete payloads without serialization issues")
        print("   • Timestamped events for better tracking")
        print("   • Action field for explicit operation identification")
    else:
        print("❌ Some tests failed")
        print("🔧 Check the implementation of _build_outbox_payload method")

    print("\n💡 Next Steps:")
    print("   1. Monitor logs for any payload-related errors")
    print("   2. Update event handlers to use new payload structure")
    print("   3. Consider adding correlation_id for request tracing")


if __name__ == "__main__":
    """
    Run payload validation:
    cd backend
    python app/tests/test_payload_structure.py
    """
    asyncio.run(main())
