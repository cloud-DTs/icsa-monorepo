import copy
import json
from pathlib import Path

import pytest

from simulator.domain import Twin


def device(device_id="sensor-a", type_id=None, properties=None):
    result = {
        "id": device_id,
        "properties": properties if properties is not None else [
            {"name": "temperature", "dataType": "DOUBLE"},
        ],
    }
    if type_id is not None:
        result["componentTypeId"] = type_id
    return result


def component(device_id="sensor-a", type_id=None, name="sensor"):
    result = {"type": "component", "name": name}
    if device_id is not None:
        result["iotDeviceId"] = device_id
    if type_id is not None:
        result["componentTypeId"] = type_id
    return result


def entity(children, entity_id="root"):
    return {"type": "entity", "id": entity_id, "name": entity_id, "children": children}


@pytest.fixture
def load_twin(tmp_path):
    def load(devices, hierarchy, twin=None):
        values = (
            {"digital_twin_name": "dt"},
            devices,
            hierarchy,
        )
        paths = [tmp_path / name for name in ("config.json", "devices.json", "hierarchy.json")]
        for path, value in zip(paths, values):
            path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        twin = twin if twin is not None else Twin()
        twin.read_from_json(*paths)
        return twin
    return load


@pytest.mark.parametrize("type_id", [None, "pac-sensor", "dt-pac-sensor"])
def test_explicit_device_keeps_identity_and_uses_logical_type_name(load_twin, type_id):
    twin = load_twin([device()], [entity([component(type_id=type_id)])])
    _, bound, attribute = twin.flatten()[0]
    assert bound.iotDeviceId == "sensor-a"
    assert bound.componentTypeId == "dt-" + (type_id or "sensor-a")
    assert attribute.name == "temperature"


@pytest.mark.parametrize("type_id", [None, "pac-sensor", "dt-pac-sensor"])
def test_type_only_reference_resolves_unique_configured_device(load_twin, type_id):
    full_type_id = "dt-" + (type_id or "sensor-a")
    twin = load_twin(
        [device(type_id=type_id)],
        [entity([component(device_id=None, type_id=full_type_id)])],
    )
    _, bound, _ = twin.flatten()[0]
    assert (bound.iotDeviceId, bound.componentTypeId) == ("sensor-a", full_type_id)


def test_hierarchy_alias_is_applied_before_resolving_an_earlier_root(load_twin):
    twin = load_twin(
        [device(type_id="previous-type")],
        [entity([component(None, "dt-pac-sensor")], "first"),
         entity([component(type_id="pac-sensor")], "second")],
    )
    assert [bound.iotDeviceId for _, bound, _ in twin.flatten()] == ["sensor-a", "sensor-a"]


def test_shared_type_keeps_separate_devices_and_attribute_state(load_twin):
    twin = load_twin(
        [device("sensor-a"), device("sensor-b")],
        [entity([component("sensor-a", "shared", "A"), component("sensor-b", "shared", "B")])],
    )
    rows = twin.flatten()
    assert [bound.iotDeviceId for _, bound, _ in rows] == ["sensor-a", "sensor-b"]
    assert {bound.componentTypeId for _, bound, _ in rows} == {"dt-shared"}
    assert rows[0][2].id != rows[1][2].id
    rows[0][2].run = True
    assert rows[1][2].run is False


def test_ambiguous_type_requires_an_explicit_device(load_twin):
    with pytest.raises(ValueError, match="shared.*iotDeviceId"):
        load_twin(
            [device("sensor-a", "shared"), device("sensor-b", "shared")],
            [entity([component(None, "dt-shared")])],
        )


@pytest.mark.parametrize("type_id", ["external-type", "dt-external-type"])
def test_external_type_is_preserved_without_simulated_attributes(load_twin, type_id):
    twin = load_twin([], [entity([component(None, type_id)])])
    assert twin.flatten() == []
    _, bound = twin.components()[0]
    assert bound.iotDeviceId is None
    assert bound.componentTypeId == type_id


def test_unknown_device_is_an_error_instead_of_an_empty_simulation(load_twin):
    with pytest.raises(ValueError, match="unknown.*missing"):
        load_twin([device()], [entity([component("missing")])])


def test_nested_device_config_loads_properties_and_infers_device(load_twin):
    tree = [entity([entity([{
        **component(type_id="pac-sensor"),
        "properties": [{"name": "samples", "dataType": "VECTOR_DOUBLE"}],
    }], "child")])]
    twin = load_twin(tree, [entity([component(None, "dt-pac-sensor")])])
    _, bound, attribute = twin.flatten()[0]
    assert bound.iotDeviceId == "sensor-a"
    assert (attribute.name, attribute.dataType.value) == ("samples", "VECTOR_DOUBLE")


def test_conflicting_duplicate_device_ids_are_rejected(load_twin):
    with pytest.raises(ValueError, match="Duplicate.*sensor-a"):
        load_twin([device(), device(type_id="another-type")], [])


@pytest.mark.parametrize("second_properties", [
    [{"name": "temperature", "dataType": "STRING"}],
    [{"name": "temperature", "dataType": "VECTOR_DOUBLE"}],
    [{"name": "pressure", "dataType": "DOUBLE"}],
])
def test_shared_types_reject_conflicting_schemas_even_without_hierarchy(load_twin, second_properties):
    with pytest.raises(ValueError, match="different properties.*sensor-a.*sensor-b"):
        load_twin([device("sensor-a", "shared"), device("sensor-b", "shared", second_properties)], [])


def test_schema_comparison_ignores_property_order_and_initial_values(load_twin):
    properties = [{"name": "temperature", "dataType": "DOUBLE", "initValue": 1},
                  {"name": "status", "dataType": "STRING", "initValue": "ready"}]
    other_properties = copy.deepcopy(list(reversed(properties)))
    other_properties[1]["initValue"] = 2
    twin = load_twin(
        [device("sensor-a", "shared", properties), device("sensor-b", "shared", other_properties)],
        [entity([component("sensor-a", "shared", "A"), component("sensor-b", "shared", "B")])],
    )
    assert len(twin.flatten()) == 4


def test_loading_twice_replaces_previous_entities(load_twin):
    twin = load_twin([device()], [entity([component()])])
    load_twin([device("sensor-b")], [entity([component("sensor-b")])], twin=twin)
    assert len(twin.flatten()) == 1
    assert twin.flatten()[0][1].iotDeviceId == "sensor-b"


def test_existing_battery_input_still_loads():
    folder = Path(__file__).resolve().parents[1] / "input"
    twin = Twin()
    twin.read_from_json(folder / "config.json", folder / "config_iot_devices.json", folder / "config_hierarchy.json")
    assert len(twin.flatten()) == 5


def test_shared_type_example_loads_two_distinct_devices():
    folder = Path(__file__).resolve().parents[1] / "input" / "shared-component-type"
    twin = Twin()
    twin.read_from_json(folder / "config.json", folder / "config_iot_devices.json", folder / "config_hierarchy.json")
    assert [bound.iotDeviceId for _, bound, _ in twin.flatten()] == ["sensor-a", "sensor-b"]
    assert {bound.componentTypeId for _, bound, _ in twin.flatten()} == {"shared-demo-temperature-sensor"}


def test_schema_validation_includes_type_assignments_from_hierarchy(load_twin):
    with pytest.raises(ValueError, match="different properties"):
        load_twin(
            [device("sensor-a"), device("sensor-b", properties=[{"name": "status", "dataType": "STRING"}])],
            [entity([component("sensor-a", "shared", "A"), component("sensor-b", "shared", "B")])],
        )


def test_equal_duplicate_devices_are_loaded_once(load_twin):
    twin = load_twin([device(), device()], [entity([component()])])
    assert len(twin.flatten()) == 1


def test_nested_hierarchy_preserves_unicode_names(load_twin):
    twin = load_twin([device()], [entity([entity([component(name="Датчик")], "Дочірній вузол")])])
    parent, bound, _ = twin.flatten()[0]
    assert (parent.name, bound.name) == ("Дочірній вузол", "Датчик")


def test_failed_reload_preserves_previous_simulation(load_twin):
    twin = load_twin([device()], [entity([component()])])
    previous_attribute = twin.flatten()[0][2]
    with pytest.raises(ValueError, match="unknown"):
        load_twin([device()], [entity([component("missing")])], twin=twin)
    assert twin.flatten()[0][2] is previous_attribute
