"""
VP CTRL v2 — Builders de mensagens WebSocket UE5.
"""
import uuid
from config.settings import BP_ACTOR_PATH, PRESET_NAME


def _new_id() -> str:
    return str(uuid.uuid4())


def get_property(property_name: str, object_path: str = None) -> dict:
    return {
        "MessageName": "object.property",
        "Id": _new_id(),
        "Parameters": {
            "ObjectPath": object_path or BP_ACTOR_PATH,
            "PropertyName": property_name,
            "Access": "READ_ACCESS",
        },
    }


def set_property(property_name: str, value, object_path: str = None) -> dict:
    return {
        "MessageName": "object.property",
        "Id": _new_id(),
        "Parameters": {
            "ObjectPath": object_path or BP_ACTOR_PATH,
            "PropertyName": property_name,
            "PropertyValue": {property_name: value},
            "Access": "WRITE_ACCESS",
        },
    }
