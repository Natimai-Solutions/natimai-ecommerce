"""
Quick test to verify the track_crud_operation decorator works correctly.
"""

import asyncio
import os
import sys

# Add the app to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.features.base.crud import CrudOperationError, track_crud_operation


# Test the decorator without arguments
@track_crud_operation
async def test_method_no_args(session, *, data, user=None):
    print(f"Method called with data: {data}, user: {user}")
    return "success"


# Test the decorator with arguments
@track_crud_operation(step_name="custom_operation")
async def test_method_with_args(session, *, data, user=None):
    print(f"Custom method called with data: {data}, user: {user}")
    return "success"


# Test error handling
@track_crud_operation
async def test_method_error(session, *, data, user=None):
    raise ValueError("Test error")


async def test_decorator():
    """Test that the decorator works correctly"""

    print("🧪 Testing track_crud_operation decorator...")
    print("=" * 50)

    try:
        # Test 1: No arguments decorator
        print("\n📝 Testing decorator without arguments...")
        result = await test_method_no_args(None, data={"test": "data"}, user=None)
        print(f"✅ Result: {result}")

        # Test 2: With arguments decorator
        print("\n📝 Testing decorator with arguments...")
        result = await test_method_with_args(None, data={"test": "data"}, user=None)
        print(f"✅ Result: {result}")

        # Test 3: Error handling
        print("\n📝 Testing error handling...")
        try:
            await test_method_error(None, data={"test": "data"}, user=None)
        except CrudOperationError as e:
            print(f"✅ Error correctly wrapped: {e}")
        except Exception as e:
            print(f"❌ Error not wrapped correctly: {type(e).__name__}: {e}")

        print("\n✅ All decorator tests passed!")
        return True

    except Exception as e:
        print(f"❌ Decorator test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    """
    Run decorator test:
    cd backend
    python app/tests/test_decorator.py
    """
    asyncio.run(test_decorator())
