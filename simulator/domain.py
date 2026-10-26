import json
import uuid
from enum import Enum

from .configuration import DeviceRegistry


class DataType(Enum):
    INTEGER = "INTEGER"
    DOUBLE = "DOUBLE"
    STRING = "STRING"
    VECTOR_DOUBLE = "VECTOR_DOUBLE"
    VECTOR_STRING = "VECTOR_STRING"
    VECTOR_INTEGER = "VECTOR_INTEGER"


class Attribute:
    def __init__(self):
        self.name: str = ""
        self.dataType: DataType = DataType.STRING
        self.id: str = uuid.uuid4().hex
        self.run = False

    def read_from_json(self, attribute: dict):
        self.name = attribute["name"]
        self.dataType = DataType(attribute.get("dataType", ""))


class Component:
    def __init__(self):
        self.iotDeviceId: str | None = None
        self.componentTypeId: str = ""
        self.name: str = ""
        self.attributes: list[Attribute] = []

    def read_from_json(self, component: dict, devices: DeviceRegistry):
        self.iotDeviceId, self.componentTypeId = devices.resolve(component)
        self.name = component["name"]
        self.attributes = []
        if self.iotDeviceId is None:
            return
        comp_data = devices.devices[self.iotDeviceId]
        for attribute in comp_data.get("properties", []):
            attr = Attribute()
            attr.read_from_json(attribute)
            self.attributes.append(attr)


class Entity:
    def __init__(self):
        self.id: str = ""
        self.name: str = ""
        self.entities: list["Entity"] = []
        self.components: list[Component] = []

    def read_from_json(self, entity: dict, devices: DeviceRegistry):
        self.id = entity["id"]
        self.name = entity["name"]
        self.entities = []
        self.components = []
        for child in entity.get("children", []):
            if child["type"] == "entity":
                ent = Entity()
                ent.read_from_json(child, devices)
                self.entities.append(ent)
            else:
                component = Component()
                component.read_from_json(child, devices)
                self.components.append(component)


class Twin:
    def __init__(self):
        self.name: str = ""
        self.entities: list[Entity] = []

    def read_from_json(self, config_json_path: str, config_iotdevices_path: str, config_hier_path: str):
        with open(config_json_path, encoding="utf-8-sig") as f:
            config_json = json.load(f)
        with open(config_iotdevices_path, encoding="utf-8-sig") as f:
            config_iotdevices = json.load(f)
        with open(config_hier_path, encoding="utf-8-sig") as f:
            config_hier = json.load(f)

        twin_name = config_json["digital_twin_name"]
        devices = DeviceRegistry(twin_name, config_iotdevices, config_hier)
        entities = []
        for entity in config_hier:
            ent = Entity()
            ent.read_from_json(entity, devices)
            entities.append(ent)
        self.name = twin_name
        self.entities = entities

    def components(self, entities: list = None):
        if entities is None:
            entities = self.entities

        rows = []
        for entity in entities:
            for component in entity.components:
                rows.append((entity, component))
            rows.extend(self.components(entity.entities))
        return rows

    def flatten(self, entities: list = None):
        return [(entity, component, attribute)
                for entity, component in self.components(entities)
                for attribute in component.attributes]
