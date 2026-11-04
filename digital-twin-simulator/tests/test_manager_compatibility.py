"""Configuration cases supported by the current digital-twin-manager."""
import pytest

from test_configuration import component, device, entity, load_twin


@pytest.mark.parametrize("data_type", [
    "BOOLEAN", "DOUBLE", "INTEGER", "LONG", "STRING",
    "VECTOR_DOUBLE", "VECTOR_INTEGER", "VECTOR_STRING",
])
def test_manager_property_types_load(load_twin, data_type):
    twin = load_twin(
        [device(properties=[{"name": "value", "dataType": data_type}])],
        [entity([component()])],
    )
    assert twin.flatten()[0][2].dataType.value == data_type


def test_entity_name_defaults_to_its_id(load_twin):
    child = entity([component()], "child")
    root = entity([child])
    del root["name"]
    del child["name"]
    twin = load_twin([device()], [root])
    assert twin.entities[0].name == "root"
    assert twin.flatten()[0][0].name == "child"


def test_aliases_of_one_device_share_simulation_state(load_twin):
    twin = load_twin([device()], [
        entity([component(name="A")], "first"),
        entity([component(name="B")], "second"),
    ])
    rows = twin.flatten()
    assert rows[0][2] is rows[1][2]
    rows[0][2].run = True
    assert rows[1][2].run is True


@pytest.mark.parametrize("name", ["iotDeviceId", "time"])
def test_routing_fields_cannot_be_simulated_properties(load_twin, name):
    with pytest.raises(ValueError, match="reserved"):
        load_twin([device(properties=[{"name": name, "dataType": "STRING"}])], [entity([component()])])


def test_duplicate_property_names_are_rejected(load_twin):
    with pytest.raises(ValueError, match="Duplicate property"):
        load_twin([device(properties=[{"name": "power", "dataType": "DOUBLE"}] * 2)], [entity([component()])])
