"""
Quick test to verify the data handling fix works with both SQLModel objects and dictionaries.
"""
import sys
import os

# Add the app to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.features.base.crud import CrudBase
from sqlmodel import SQLModel, Field
from typing import Optional


# Mock models for testing
class TestModel(SQLModel, table=True):
    __tablename__ = "test_table"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    value: int


class TestCreateSchema(SQLModel):
    name: str
    value: int


class TestUpdateSchema(SQLModel):
    name: Optional[str] = None
    value: Optional[int] = None


def test_data_extraction():
    """Test that _extract_data_dict works with both SQLModel and dict"""
    
    print("🧪 Testing data extraction methods...")
    print("=" * 50)
    
    # Create a test CRUD instance
    crud = CrudBase(
        model=TestModel,
        schema_create=TestCreateSchema,
        schema_update=TestUpdateSchema
    )
    
    try:
        # Test 1: SQLModel object
        print("\n📝 Testing with SQLModel object...")
        schema_obj = TestCreateSchema(name="test", value=42)
        result = crud._extract_data_dict(schema_obj)
        print(f"✅ SQLModel result: {result}")
        assert isinstance(result, dict), "Result should be a dictionary"
        assert result["name"] == "test", "Name should be preserved"
        assert result["value"] == 42, "Value should be preserved"
        
        # Test 2: Dictionary
        print("\n📝 Testing with dictionary...")
        dict_data = {"name": "test_dict", "value": 100}
        result = crud._extract_data_dict(dict_data)
        print(f"✅ Dictionary result: {result}")
        assert isinstance(result, dict), "Result should be a dictionary"
        assert result["name"] == "test_dict", "Name should be preserved"
        assert result["value"] == 100, "Value should be preserved"
        
        # Test 3: Invalid data
        print("\n📝 Testing with invalid data...")
        result = crud._extract_data_dict("invalid")
        print(f"✅ Invalid data result: {result}")
        assert result == {}, "Invalid data should return empty dict"
        
        print("\n✅ All data extraction tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Data extraction test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_payload_building():
    """Test that _build_outbox_payload works correctly"""
    
    print("\n🧪 Testing payload building...")
    print("=" * 50)
    
    # Create a test CRUD instance
    crud = CrudBase(
        model=TestModel,
        schema_create=TestCreateSchema,
        schema_update=TestUpdateSchema
    )
    
    try:
        # Mock record
        class MockRecord:
            id = 123
            name = "test"
            value = 42
        
        record = MockRecord()
        
        # Test with dictionary data
        data = {"name": "updated", "value": 99}
        
        payload = crud._build_outbox_payload(
            action="update",
            record=record,
            user=None,
            data=data
        )
        
        print(f"✅ Payload structure: {payload}")
        
        # Validate payload structure
        required_fields = ["id", "model", "action", "timestamp"]
        for field in required_fields:
            assert field in payload, f"Payload missing required field: {field}"
        
        assert payload["action"] == "update", "Action should be 'update'"
        assert payload["id"] == "123", "ID should be string '123'"
        assert payload["data"] == data, "Data should match input"
        
        print("\n✅ Payload building test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Payload building test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    """
    Run data handling tests:
    cd backend
    python app/tests/test_data_handling.py
    """
    
    print("🚀 CRUD Data Handling Tests")
    print("=" * 50)
    
    # Test 1: Data extraction
    extraction_ok = test_data_extraction()
    
    # Test 2: Payload building
    payload_ok = test_payload_building()
    
    # Summary
    print(f"\n📋 Test Results Summary:")
    print("=" * 50)
    
    if extraction_ok and payload_ok:
        print("✅ Data extraction: WORKING")
        print("✅ Payload building: WORKING")
        print("✅ Both SQLModel and dict support: IMPLEMENTED")
        print("\n🎯 The AttributeError should now be resolved!")
    else:
        print("❌ Some tests failed")
        print("🔧 Check the _extract_data_dict implementation")
    
    print(f"\n💡 Next Steps:")
    print("   1. Test with actual payment CRUD operations")
    print("   2. Verify outbox events are created correctly")
    print("   3. Monitor for any remaining AttributeError issues")