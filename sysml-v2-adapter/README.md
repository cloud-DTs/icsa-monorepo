# DigitalTwinSysmlv2CM

Converts SysML v2 digital twin models into the JSON configuration of the deployer.

The models are read and validated by the [DigitalTwinProfileSysmlv2JavaLibrary](https://github.com/cloud-DTs/DigitalTwinProfileSysmlv2JavaLibrary). How to model twins, entities, components, attributes, conditions and strategy actions is described in the README of that repository.

# Requirements

* Python 3
* Java 21 (JDK, a newer version works as well)
* Maven on the `PATH` (`mvn -v` must work)

Docker and the SysML API server are no longer needed.

# Usage

```bash
python main.py <sysml file or directory>... [-o <output directory>]
```

* Every input may be a `.sysml` file or a directory; all `.sysml` files below a directory are read.
* All inputs are parsed together in one run, so models may reference each other across files.
* `-o` sets the output directory, the default is `output`.

Examples:

```bash
python main.py ./Test.sysml
python main.py ./models/MGrid.sysml ./models/shared/ -o ./deploy
```

On the first run `main.py` builds the exporter in `exporter/` with Maven. Maven downloads the library and its dependencies once; later runs only start the exporter.

# Output

Every twin (`#Twin def`) gets its own folder, named after the id of the twin. `twins.json` lists all twins of the run:

```
output/
├── twins.json
├── Ci2d6P5WvYTHNNrfqgTZH7/
│   ├── config.json
│   ├── config_hierarchy.json
│   ├── config_events.json
│   └── config_iot_devices.json
└── ...
```

```json
[
    {
        "name": "MGrid",
        "id": "Ci2d6P5WvYTHNNrfqgTZH7",
        "folder": "Ci2d6P5WvYTHNNrfqgTZH7"
    }
]
```

Read `twins.json` to find the folder of a twin; twins with the same name in different packages get different folders.

| File | Content |
|---|---|
| `config.json` | twin name and storage retention |
| `config_hierarchy.json` | entities with their components |
| `config_iot_devices.json` | one device per component with its measure attributes; the const attributes of an entity form the device `<entityId>const_component` |
| `config_events.json` | one event per strategy action of a condition, with the condition as `<entityId>.<component>.<attribute> <operator> ...` |


Values that are not written in the model are filled in by the exporter:

* storage retention: 30 days,
* feedback topic type: `NOFEEDBACK`,
* data type of an attribute: `STRING`.

Twins whose name is longer than 10 characters are skipped with a warning, because the deployer does not accept them.

# Ids

Ids are the deterministic ids of the parser, shortened to 22 characters (base57, like Python `shortuuid`). The same model gives the same ids on every run and on every machine, also when it is split differently across files or the files are read in another order. An id only changes when the model itself changes.
(IMPORTANT) when you have unnamed things in the model, then ids can change if the position of that changes

# Errors

The exporter stops with a message when the model is invalid, for example

* a SysML error or warning,
* an element that does not fit the DigitalTwinLibrary,
* a missing required value of a strategy action,
* a `customPayload` that is no valid JSON,
* a const value that does not match its data type (`"15.0"` for `INTEGER`).

A `pathToCode` that does not exist on the machine only gives a warning.