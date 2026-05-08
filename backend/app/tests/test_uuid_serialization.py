"""
Test de sérialisation JSON pour les UUID et datetime
"""

import datetime
import uuid

from sqlmodel import SQLModel

from app.features.base.crud import CrudBase


class _DummyModel(SQLModel):
    pass


def test_json_serialization():
    """Test que la sérialisation JSON gère correctement UUID et datetime"""

    # Créer une instance du CRUD pour accéder à la méthode
    crud = CrudBase(
        model=_DummyModel,
        schema_create=_DummyModel,
        schema_update=_DummyModel,
    )

    # Data avec UUID et datetime
    test_data = {
        "id": uuid.uuid4(),
        "name": "Test Product",
        "created_at": datetime.datetime.now(datetime.timezone.utc),
        "price": 19.99,
        "nested": {
            "user_id": uuid.uuid4(),
            "updated_at": datetime.datetime.now(datetime.timezone.utc),
        },
        "tags": [
            {"tag_id": uuid.uuid4(), "name": "electronics"},
            {"tag_id": uuid.uuid4(), "name": "mobile"},
        ],
    }

    # Sérialiser
    serialized = crud._serialize_for_json(test_data)

    # Vérifier que les UUID sont convertis en strings
    assert isinstance(serialized["id"], str)
    assert isinstance(serialized["nested"]["user_id"], str)
    assert isinstance(serialized["tags"][0]["tag_id"], str)

    # Vérifier que les datetime sont convertis en ISO strings
    assert isinstance(serialized["created_at"], str)
    assert isinstance(serialized["nested"]["updated_at"], str)

    # Vérifier que les autres types sont préservés
    assert isinstance(serialized["name"], str)
    assert isinstance(serialized["price"], float)

    print("✅ Test de sérialisation JSON réussi!")
    print(f"Original UUID: {test_data['id']}")
    print(f"Serialized UUID: {serialized['id']}")
    print(f"Original datetime: {test_data['created_at']}")
    print(f"Serialized datetime: {serialized['created_at']}")


if __name__ == "__main__":
    test_json_serialization()
