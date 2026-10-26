# Digital Twin Simulator Manager

Generate device data for Cloud Deployer configurations. The interface shows each
component's device ID, full Component Type ID, and properties.

## Local setup

Use Python 3.12 or later. Run these commands from the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

$env:CONFIG_JSON_PATH = './input/config.json'
$env:CONFIG_HIERARCHY_JSON_PATH = './input/config_hierarchy.json'
$env:CONFIG_IOT_JSON_PATH = './input/config_iot_devices.json'
$env:SIMULATOR_MOCK_AWS = 'true'
python main.py
```

Open http://localhost:5000. On Linux or macOS, activate the environment with
`source .venv/bin/activate` and set the same variables with `export`.

In mock mode, generated messages go to the process log. To publish to AWS, set
`SIMULATOR_MOCK_AWS=false` and supply AWS credentials with `iot:Publish` access to
the twin's topic. Set `AWS_REGION` to the deployment region. The simulator uses
one `boto3 iot-data` client and AWS credentials. It does not use device certificates.

## Configuration and shared types

The simulator reads `config.json`, `config_iot_devices.json`, and
`config_hierarchy.json`. Device configuration can be a flat device list or an
entity tree with device properties on component nodes.

For twin `dt`, hierarchy references follow these rules:

| Component fields | Full Component Type ID | Device binding |
|---|---|---|
| `iotDeviceId: sensor-a` | `dt-sensor-a` | `sensor-a` |
| `iotDeviceId: sensor-a`, `componentTypeId: shared` | `dt-shared` | `sensor-a` |
| `componentTypeId: dt-shared` | `dt-shared` | The only configured device for this type |

With an explicit device ID, the type name is logical. The twin prefix is always
added, including when the logical name already starts with that prefix.
Without a device ID, the type ID is the full AWS ID and is used as supplied.
Hierarchy type names override type names in device configuration before bindings
are resolved across all root entities.

A type shared by several devices needs an explicit `iotDeviceId` on each
hierarchy component. Unknown device IDs, conflicting duplicate device
configurations, and incompatible shared schemas stop loading with an error.
Shared schemas must have the same property names and data types. Property order
and per-device `initValue` values can differ. Initial values do not select a
simulation mode or set the generator's start value.

A full type ID absent from the configured device types is an external reference.
The interface shows its status without simulation controls or AWS lookup.

All devices publish to `<digital_twin_name>/iot-data`. Each message contains
`iotDeviceId`, `time`, and the generated property. Shared types retain separate
device IDs and controls. Cloud Deployer manages one shared IoT policy per twin;
each device retains its own Thing and certificate. Debug ingestion timing fields
are added by the cloud pipeline.

## Docker and the shared-type example

```powershell
docker compose up --build
```

The default configuration is in `input/`. To run the two-device example:

```powershell
$env:SIMULATOR_INPUT_HOST_DIR = './input/shared-component-type'
docker compose up --build
```

To use the manager's configuration files, set `SIMULATOR_INPUT_HOST_DIR` to their
directory, for example `../digital-twin-manager`. Docker mounts the three files
as read-only files. For a local Python run, set the three `CONFIG_*_PATH` variables
to files in the selected directory.

## Tests

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests use temporary configuration files and a local AWS substitute. They do not
publish to AWS.
