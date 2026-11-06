# DigitalTwinSysmlv2CM

> **Note:** Ignore the run instructions in this README. Use the tool through the [`reproduce`](../reproduce/README.md) setup, which builds it and runs it together with the evaluator.

Reads SysML v2 digital twin models and prepares them for the deployer.

The models are read and validated by the libraries in [`lib/`](lib/): [`sysml-digital-twin-profile`](lib/sysml-digital-twin-profile/README.md) defines the roles, and [`sysml-library-mapper`](lib/sysml-library-mapper/README.md) reads and checks the SysML. The role definitions are in [`DigitalTwinLibrary.sysml`](lib/sysml-digital-twin-profile/DTLibrary/DigitalTwinLibrary.sysml).

# Modeling the roles

A definition uses the capitalized keyword, a usage the lowercase one, for example `#Entity def Charger` and `#entity charger1 : Charger`. Values are set with `:>>`.

| Role | Keywords | Slots | In the deployed twin |
| --- | --- | --- | --- |
| Twin | `#Twin def` | `hotDatabaseRetentionDays`, `coldDatabaseRetentionDays` (days, default 30); contains entities and conditions | the twin: its workspace and the hot and cold storage with their retention |
| Entity | `#Entity def`, `#entity` | nested entities, components, const attributes | an entity in TwinMaker |
| Component | `#Component def`, `#component` | measure attributes | a connected device with its message processing, and a TwinMaker component |
| MeasureAttribute | `#measureAttribute` | `dataType`: `STRING` (default), `DOUBLE`, `INTEGER` or a `VECTOR_*` type | a measured property of the device |
| ConstAttribute | `#constAttribute` | `dataType`, `value` (a string literal) | a constant of the entity, set as initial value |
| Condition | `#condition` | `leftOperand`, `operator`, `rightOperand`; contains strategy actions | a condition that the Event Checker evaluates |
| StrategyAction | `#strategyAction` | `name`, `pathToCode`, `external`, `strategyType` (`LAMBDA`); optional `inputParameters`, `outputParameters`, `customPayload`, `feedbackTopicType` (`EXTERN`, `INTERN` or `NOFEEDBACK`, default `NOFEEDBACK`), `componentTopic`, `externalTopic` | an action function and its feedback |

The operands, the parameters and `componentTopic` are references to attributes and components of the twin. The deployer accepts the operators `GREATER_THAN`, `LESS_THAN` and `EQUAL`. The library also defines `GREATER_EQUAL`, `LESS_EQUAL` and `NOT_EQUAL`, which the deployer rejects. A condition and its action in [`MGridICSA.sysml`](../reproduce/models/MGridICSA.sysml), shortened:

```sysml
#condition charger1Changed : ChargerChanged {
    :>> leftOperand = MicroGrid.charger1.p13.power;
    :>> operator = ComparisonOperator::GREATER_THAN;
    :>> rightOperand = MicroGrid.chargingThreshold;
    balance1 :>> balance {
        charger1Power :>> inputParameters = MicroGrid.charger1.p13.power;
        :>> componentTopic = MicroGrid.battery.controller;
    }
}
```

The Event Checker evaluates the condition when a stored message contains the property of one of its operands. If the condition holds, the action receives the input parameters, and its result is sent as feedback to the topic of the component. The rules that a model must satisfy are listed in [Validation](lib/sysml-digital-twin-profile/README.md#validation) of the role library.

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

The two SysML libraries it needs, `sysml-digital-twin-profile` and `sysml-library-mapper`, are part of this artifact in `lib/`. The Docker build compiles them from source. Outside Docker, build them first (see their READMEs) and install the SysML kernel jar. Maven downloads the other dependencies once; later runs only start the exporter.

# Twin names

A twin name has at most 10 characters. Twins with a longer name are skipped with a warning, because the deployer does not accept them.

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