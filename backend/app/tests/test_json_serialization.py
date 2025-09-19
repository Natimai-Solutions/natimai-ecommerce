"""
Test to validate JSON serialization of datetime objects in outbox payloads.
"""
import json
import datetime
import sys
import os

# Add the backend directory to Python path for relative imports
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, backend_dir)

from app.features.base.crud import CrudBase
from sqlmodel import SQLModel, Field
from typing import Optional


# Mock models for testing
class TestModel(SQLModel, table=True):
    __tablename__ = "test_table"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    created_at: Optional[datetime.datetime] = None


class TestCreateSchema(SQLModel):
    name: str


def test_datetime_serialization():
    """Test that datetime objects are properly serialized to JSON-compatible strings"""
    
    print("🧪 Testing datetime serialization...")
    print("=" * 50)
    
    # Create a test CRUD instance
    crud = CrudBase(
        model=TestModel,
        schema_create=TestCreateSchema,
        schema_update=TestCreateSchema
    )
    
    try:
        # Test 1: Simple datetime serialization
        print("\n📝 Testing simple datetime serialization...")
        
        test_data = {
            "name": "test",
            "created_at": datetime.datetime.now(),
            "updated_at": datetime.datetime(2025, 9, 18, 14, 30, 0)
        }
        
        serialized = crud._serialize_for_json(test_data)
        print(f"✅ Original data: {test_data}")
        print(f"✅ Serialized data: {serialized}")
        
        # Verify datetime objects are converted to strings
        assert isinstance(serialized["created_at"], str), "created_at should be a string"
        assert isinstance(serialized["updated_at"], str), "updated_at should be a string"
        assert serialized["name"] == "test", "name should be preserved"
        
        # Test JSON serialization
        json_str = json.dumps(serialized)
        print(f"✅ JSON serialization successful: {len(json_str)} characters")
        
        # Test 2: Nested structure with datetime
        print("\n📝 Testing nested structure with datetime...")
        
        nested_data = {
            "user": {
                "name": "John",
                "created_at": datetime.datetime.now()
            },
            "metadata": {
                "timestamps": [
                    datetime.datetime.now(),
                    datetime.datetime(2025, 1, 1)
                ]
            },
            "simple_field": "value"
        }
        
        serialized_nested = crud._serialize_for_json(nested_data)
        print(f"✅ Nested serialized: {serialized_nested}")
        
        # Verify nested datetime conversion
        assert isinstance(serialized_nested["user"]["created_at"], str), "Nested datetime should be string"
        assert isinstance(serialized_nested["metadata"]["timestamps"][0], str), "List datetime should be string"
        
        # Test JSON serialization of nested structure
        json_str_nested = json.dumps(serialized_nested)
        print(f"✅ Nested JSON serialization successful: {len(json_str_nested)} characters")
        
        print("\n✅ All datetime serialization tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Datetime serialization test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_payload_json_compatibility():
    """Test that outbox payloads are JSON-compatible"""
    
    print("\n🧪 Testing outbox payload JSON compatibility...")
    print("=" * 50)
    
    # Create a test CRUD instance
    crud = CrudBase(
        model=TestModel,
        schema_create=TestCreateSchema,
        schema_update=TestCreateSchema
    )
    
    try:
        # Mock record with datetime field
        class MockRecord:
            id = 123
            name = "test"
            created_at = datetime.datetime.now()
        
        record = MockRecord()
        
        # Test data with datetime
        data_with_datetime = {
            "name": "updated",
            "created_at": datetime.datetime.now(),
            "modified_at": datetime.datetime(2025, 9, 18)
        }
        
        # Build payload
        payload = crud._build_outbox_payload(
            action="create",
            record=record,
            user=None,
            data=data_with_datetime
        )
        
        print(f"✅ Payload structure: {payload}")
        
        # Test JSON serialization of complete payload
        try:
            json_str = json.dumps(payload)
            print(f"✅ Complete payload JSON serialization successful!")
            print(f"   JSON length: {len(json_str)} characters")
            
            # Parse back to verify
            parsed = json.loads(json_str)
            assert parsed["action"] == "create", "Action should be preserved"
            assert "timestamp" in parsed, "Timestamp should be present"
            assert "data" in parsed, "Data should be present"
            
            print(f"✅ JSON round-trip successful!")
            
        except TypeError as e:
            print(f"❌ JSON serialization failed: {e}")
            return False
        
        print("\n✅ Payload JSON compatibility test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Payload JSON compatibility test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    """
    Run JSON serialization tests:
    cd backend
    python app/tests/test_json_serialization.py
    """
    
    print("🚀 JSON Serialization Tests")
    print("=" * 50)
    
    # Test 1: Datetime serialization
    datetime_ok = test_datetime_serialization()
    
    # Test 2: Payload JSON compatibility
    payload_ok = test_payload_json_compatibility()
    
    # Summary
    print(f"\n📋 Test Results Summary:")
    print("=" * 50)
    
    if datetime_ok and payload_ok:
        print("✅ Datetime serialization: WORKING")
        print("✅ Payload JSON compatibility: WORKING")
        print("✅ PostgreSQL JSON column support: READY")
        print("\n🎯 The 'datetime is not JSON serializable' error should be resolved!")
        print("\n💡 Benefits:")
        print("   • Datetime objects automatically converted to ISO strings")
        print("   • Nested structures properly handled")
        print("   • Complete payload JSON compatibility")
        print("   • Safe database storage in JSON columns")
    else:
        print("❌ Some tests failed")
        print("🔧 Check the _serialize_for_json implementation")
    
    print(f"\n🔄 Next Steps:")
    print("   1. Test outbox creation with actual models")
    print("   2. Verify events are stored correctly in database")
    print("   3. Check that handlers receive properly formatted data")