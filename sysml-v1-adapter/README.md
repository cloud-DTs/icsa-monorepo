# Documentation

## Prerequisites

### Technologies
- **Java 25**
- **XMI 2.1 file** containing a **SysML v1 model** exported from *Enterprise Architect*² and annotated with the **DigitalTwinProfile**.  
  This file serves as the input for the program.

## Architecture

The purpose of this tool is to parse a SysML model annotated with the **DigitalTwinProfile** and convert it into a structure that serves as input for the **digital-twin-manager**¹, which deploys digital twins to AWS.

<img src="./documentationContent/DigitalTwins.png" alt="Architecture Diagram">

### Input Requirements
- **Twin name** (maximum length: 10 characters)
- **XMI 2.1 model file** from *Enterprise Architect*², annotated with the **DigitalTwinProfile**

---

## The DigitalTwinProfile

The DigitalTwinProfile extends the standard **SysML v1 profile** with additional stereotypes required to construct a deployable digital twin.

### Block Definition Diagram (BDD)

<img src="./documentationContent/BddProfile.png" alt="BDD Profile">

The figure illustrates the BDD view. The following stereotypes extend SysML Blocks and are placed in the BDD:

- **Twin**  
  Marks a SysML Block as a Twin (e.g., `ECar`). A Twin may contain:
    - **Component**  
      Marks a SysML Block as a component (e.g., `Engine`).  
      Components may contain annotated attributes:
        - **MeasurementInstance**
            - Tagged Values:
                - `dataType`
        - **ConstInstance**
            - Tagged Values:
                - `dataType`
            - Has a value set directly in Enterprise Architect.
    - **Device**  
      Marks a SysML Block as a device (e.g., a sensor).
    - **Strategy**  
      Marks a SysML Block as a strategy to be executed on AWS.
        - Tagged Values:
            - `pathToCode`
            - `strategyType` (`LAMBDA` or `CONTAINER`)
    - **TwinDataBase**

#### Connectors (BDD)
The following connectors extend the SysML Aggregation Connector:

- **hasComponent** – A Twin may have multiple Components
- **hasDevice** – A Twin may have multiple Devices
- **hasStrategy** – A Twin may have multiple Strategies

A direct connection between **Twin** and **TwinDataBase** is not required; they only need to belong to the same Twin.  
A Twin may contain **at most two databases**.

---

### Internal Block Diagram (IBD)

The IBD view defines the internal structure of the Twin.
This is the actual content in AWS.
<img src="./documentationContent/IBDTwin.png" alt="IBD Twin">

The following stereotypes are provided:

- **ComponentInstance**  
  Marks a SysML part within a Twin as a component instance.  
  A component instance may override values of `ConstInstance`.
- **DeviceInstance**  
  Marks a SysML part as a device instance, capable of triggering multiple strategies or measurements.
- **StrategyInstance**  
  Marks a SysML part as a strategy instance, with the following tagged values:
    - `feedBackPayloadType`:
        - `strategyResult` – returns the strategy’s result
        - `custom` – custom defined return value
    - `feedBackTopicType`:
        - `EXTERNAL` – sends the result to an external topic
        - `INTERNAL` – uses the connector endpoint as the topic
        - `NONE` – result is ignored
    - `customPayload`
    - `customTopic`
- **DataBaseInstance**  
  Tagged Values:
    - `dataBaseTier`:
        - `HOT`
        - `COLD`  
          Exactly two databases are allowed per Twin: one HOT and one COLD.

#### Connectors (IBD)
- **measures**
    - Tagged Values:
        - `measurement` – reference to a `MeasurementInstance` of a Component  
          A `DeviceInstance` may measure **at most one** `ComponentInstance`.

- **triggers**
    - Tagged Values:
        - `lhsProperty` – reference to a `MeasurementInstance` or `ConstInstance`
        - `rhsProperty` – same type as `lhsProperty`
        - `operator` – e.g. `<`, `>`, etc.

- **feedBackTopic**
    - Used when `feedBackTopicType = INTERNAL`.  
      The connector endpoint determines the internal topic.

---

## Functionality of the Tool

The tool converts the annotated SysMl model into the target structure required by the deployment tool.  
For consistent mapping between Enterprise Architect and AWS, the **xmi:idref** of each model element is used as the identifier.  
Because AWS requires shorter identifiers, IDs are shortened in a backward-compatible manner.

---

## Container Usage

The adapter is a one-shot container: it reads one XMI model, writes the generated JSON files, and exits.

1. Copy `.env.example` to `.env`.
2. Create the configured input, output, and code directories.
3. Put the XMI file into `PIPELINE_INPUT_HOST_DIR`. Its filename must match `MODEL_FILE`.
4. On Linux, set `DTP_UID` and `DTP_GID` in `.env` to the output of `id -u` and `id -g`. This keeps generated files writable by the host user.
5. If the model contains host paths in `pathToCode`, mount their common directory through `PIPELINE_CODE_HOST_DIR` and configure `DTP_PATH_MAP`.

Example `.env` mapping for a model exported on Windows:

```dotenv
MODEL_FILE=model.xml
TWIN_NAME=dtwin
PIPELINE_CODE_HOST_DIR=C:/work/strategy-code
DTP_PATH_MAP=C:/work/strategy-code=/pipeline/code
```

Multiple path mappings are separated with `;`. Windows source paths are matched case-insensitively, and the most specific matching prefix is used.

Build and run the adapter:

```shell
docker compose run --rm --build digital-twin-profile-sysml-v1
```

Generated files are written to `PIPELINE_OUTPUT_HOST_DIR/<lowercase-TWIN_NAME>/`. The input and strategy-code mounts are read-only.

After writing the files, the parser removes the identifiers of the Enterprise Architect elements (`hot_storage_id`, `hot_storage_definition_id`, `cold_storage_id`, `cold_storage_definition_id` in `config.json` and `definitionId` in `config_hierarchy.json`), because the deployer rejects unknown keys. This is done by `TargetService/DeployerCleaner` and is a research prototype.

A small public model is in [`example/model.xml`](example/model.xml). Convert it with `MODEL_FILE=model.xml`, the code mount `../reproduce/code`, and the strategy path `/pipeline/code/microgrid/energy-management` that the model already contains.

---

## References
[1] digital-twin-manager: [`../digital-twin-manager`](../digital-twin-manager)  
[2] Enterprise Architect by Sparx Systems: https://sparxsystems.com/


