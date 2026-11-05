# DT Library Mapper

Maps SysML v2 models written against the `DigitalTwinLibrary` to Java objects. It is built on SysmlModelParser (`sysml-library-mapper`), which reads and validates the models; this project adds the library, the mapping classes and the rules of the Digital Twin profile.


# Requirements

* Java 21 (a newer runtime works as well)
* Maven

# Build

Build and install `sysml-library-mapper` first (see `../sysml-library-mapper`), then:

```shell
mvn install -Dmaven.test.skip=true
```

The Dockerfile of `sysml-v2-adapter` does both steps. The dependency of the exporter is:

```xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>sysml-digital-twin-profile</artifactId>
    <version>1.1.1</version>
</dependency>
```

# Usage

```java
DTLibraryParser parser = new DTLibraryParser();
ResultConverter result = parser.parse("path/to/model");

for (TwinDefinition twin : result.getByType(TwinDefinition.class)) {
    if (twin.isLibrary()) continue;
    twin.getEntities();
    twin.getConditions();
}
```

Create the parser once and call `parse` for every model; each call replaces the previous model. Every path may be a file or a directory, all `.sysml` files below it are read.

`parse` throws

* `IllegalStateException` when SysML reports an error or a warning (for example a value whose type does not fit),
* `IllegalArgumentException` or `IllegalStateException` when the model breaks a rule of the profile (see Validation).

# Library

`DTLibrary/DigitalTwinLibrary.sysml` defines the profile, `DTLibrary/MetaLibrary.sysml` the metadata keywords. Compared with the library of the old Python converter:

* all `default` values are removed; a value has to be written in the model,
* `outputParameters` is typed `LibDTAttributes`, like `inputParameters`,
* the enums specialize the new `abstract attribute def TwinEnum`,
* list slots carry `[0..*]` on their redefinitions, optional slots `[0..1]`.

# Modeling

Definitions use the capitalized keyword, usages the lowercase one:

```
#Entity def Charger {
    #constAttribute maxConsumption {
        :>> value = "50.0";
        :>> dataType = AttributeDataType::DOUBLE;
    }
    #component sensor : PAC_Sensor;
}

#Twin def MGrid {
    #entity Charger1 : Charger {
        p13 :>> sensor {
            #measureAttribute power { :>> dataType = AttributeDataType::DOUBLE; }
        }
    }

    #condition stopCharging : StopCharging {
        :>> leftOperand = Charger1.p13.power;
        :>> operator = ComparisonOperator::EQUAL;
        :>> rightOperand = Charger1.maxConsumption;
        :>> stopCharging {
            :>> feedbackTopicType = FeedbackTopicType::INTERN;
            :>> componentTopic = Charger1.p13;
            in1 :> inputParameters = Charger1.p13.power;
            out1 :> outputParameters = Charger1.p13.power;
        }
    }
}
```

A definition may leave slots open that a usage fills later, like `StopCharging` whose operands are set in the twin.

# Mapped classes

All classes live under `org.example.Model`. Every element offers `getId()` (deterministic UUID), `getName()`, `getParent()`, `isInherited()` and `isLibrary()` from SysmlModelParser.

| Element | Classes | Getters |
|---|---|---|
| Twin | `TwinDefinition`, `TwinUsage` | `getEntities()`, `getConditions()`, `getHotDatabaseType()`, `getHotDatabaseRetentionDays()`, `getColdDataBaseType()`, `getColdDatabaseRetentionDays()` |
| Entity | `EntityDefinition`, `EntityUsage` | `getEntities()`, `getComponents()`, `getConstAttributes()`, `getStrategies()` |
| Component | `ComponentDefinition`, `ComponentUsage` | `getMeasurements()` |
| Measure attribute | `MeasureAttributeDefinition`, `MeasureAttributeUsage` | `getDataType()` |
| Const attribute | `ConstAttributeDefinition`, `ConstAttributeUsage` | `getDataType()`, `getValue()` |
| Condition | `ConditionDefinition`, `ConditionUsage` | `getLeftOperand()`, `getOperator()`, `getRightOperand()`, `getStrategyActions()` |
| Strategy action | `StrategyActionDefinition`, `StrategyActionUsage` | `getActionName()`, `getPathToCode()`, `getExternal()`, `getStrategyType()`, `getDescription()`, `getCustomPayload()`, `getFeedbackTopicType()`, `getComponentTopic()`, `getExternalTopic()`, `getInputParameters()`, `getOutputParameters()` |

Values:

* String, Integer and Boolean attributes are `TwinAttributeStringUsage`, `TwinAttributeIntegerUsage` and `TwinAttributeBooleanUsage`; `getExpression()` holds the literal, its `getValue()` the Java value.
* Enum attributes (`EnumAttributeDataTypeUsage`, `EnumComparisonOperatorUsage`, ...) return the Java enum with `getValue()`.
* `LeftOperandUsage`, `RightOperandUsage`, `InputParameterUsage` and `OutputParameterUsage` return the referenced measure or const attribute with `getReference()`.
* `ComponentTopicUsage` returns the referenced component with `getReference()`.

A reference resolves to the mapped instance itself: `getReference()` of `Charger1.p13.power` has the same id as `power` in `getMeasurements()` of `p13`.

# Validation

Besides the SysML validation, `parse` rejects

* a feature that fits no slot of its owner, for example a `#measureAttribute` directly in an entity or a `#constAttribute` in a component,
* a value that is not a literal in a plain attribute (references and calculations),
* a value that is not a plain reference in operands, parameters and the component topic,
* a missing `name`, `pathToCode`, `external` or `strategyType` of a strategy action, and a single valued slot given twice,
* incompatible typings of one element (`MultiType`).



A `pathToCode` that does not exist on the machine running the parser only gives a warning.


# Ids

Ids are the deterministic UUIDs of SysmlModelParser: the same model gives the same ids on every run.

# Build and test

```
mvn test
mvn test -Dtest=InvalidModelTest
mvn package -DskipTests
```

The tests read the models in `src/test/resources/models/<name>/` and have to run from the project directory. In IntelliJ run the Maven phase `generate-resources` first so that `DTLibrary.zip` is on the classpath.