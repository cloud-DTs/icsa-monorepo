# SysmlModelParser

> **Note:** The [`reproduce`](../../../reproduce/README.md) setup builds this project automatically, as part of the SysML v2 parser. You do not need to build it yourself. The build instructions below are for reference.

SysmlModelParser reads SysML v2 models and turns them into Java objects. You decide with annotations which Java class is built for which SysML element. The parser finds these classes on its own by scanning the classpath at startup.

Principle: only elements that have a class are mapped. Elements without a matching class are left out of the result.

# Build

Java 21 and Maven are required. In this artifact the library is built from source by the Dockerfile of `sysml-v2-adapter` and installed into the local Maven repository, together with the SysML kernel jar (`org.omg.sysml:jupyter-sysml-kernel` 0.55.0, taken from the conda-forge package `jupyter-sysml-kernel` 0.55.0). Without Docker, install that jar and build the library:

```shell
mvn install -Dmaven.test.skip=true
```

# Entry point

```java
SysmlConverterMain main = new SysmlConverterMain("MyLibrary.zip");
ResultConverter result = main.parse("path/to/model");

List<MyPartUsage> parts = result.getByType(MyPartUsage.class);
```

`"MyLibrary.zip"` is your SysML library as a zip file on the classpath, for example in `src/main/resources`. It is loaded and validated once when `SysmlConverterMain` is created; errors in the library are thrown immediately.

`parse(String... paths)` reads all `.sysml` files below the given paths, validates them, runs the rules and maps them. One instance can be reused; every call replaces the input of the previous one.

# Mapping classes

Every mapped class extends `Definition` or `Usage` and carries exactly one annotation.

## By library type

```java
@MappedLibrary(libraryName = "MyLibrary::Sensor", core = SensorCore.class)
public class SensorUsage extends Usage<SensorCore, PartUsage, SensorDefinition> {
    public SensorUsage(PartUsage element, Mapper mapper) { super(element, mapper); }
}
```

`libraryName` is the qualified name of a type in your library. If the SysML element is a classifier, the definition class is used; if it is a feature, the usage class is used. So each library type can have one definition class and one usage class.

## By metaclass

```java
@MappedMetaClass(value = ActionUsage.class, core = MyActionCore.class)
public class MyActionUsage extends ActionMapUsage<MyActionCore> { ... }
```

`value` is a SysML metaclass (for example `ActionUsage`, `InvocationExpression`).

## Rules for mapping classes

* Exactly one public constructor `(SysML type, Mapper)`. The SysML type decides which elements the class accepts.
* `core` must be a concrete class and must fit the type parameter `C` of the class.
* The type parameter `D` of a usage (its definition) must have exactly one bound.
* Annotations are not inherited. A class without an annotation is invisible to the parser.

## Predefined classes

`Model.Predefined` contains abstract templates without annotations, for example `ActionMapUsage`, `AssignmentMapUsage`, `ForLoopMapUsage`, `FeatureReferenceUsage`, `LiteralIntegerUsage`. They only become active once you write an annotated subclass.

Slots are filled in protected `mapXxx()` methods, and the getters return wildcard types. In your subclass you override both and narrow the type:

```java
@Override
protected List<? extends Usage<?, ?, ?>> mapTarget() {
    return mapper.mapSlot("target", this, MyAttributeUsage.class);
}

@Override
public MyAttributeUsage getTarget() {
    return MyAttributeUsage.class.cast(super.getTarget());
}
```

# Resolution rules

For each element the parser looks for a class in this order:

1. **Library type.** The most specific library type the element specializes that has a class. If the constructor of that class does not accept the element, the parser moves on to the next parent library type.
2. **Metaclass.** If no library type fits, the most specific mapped metaclass the element is an instance of is used.
3. **Nothing.** The element stays unmapped and does not appear in the result.

## Subclass wins

If two classes share the same key (same metaclass, or same `libraryName` and same kind, definition or usage):

* If one is a subclass of the other, the subclass replaces the parent class. This lets another library extend an existing mapping.
* If they are unrelated, the scan fails with an error.

## Warning: metaclasses are broad

Many SysML metaclasses inherit from each other. A mapping on a general metaclass also catches every subtype that has no mapping of its own. Examples:

* `ActionUsage` also catches `CalculationUsage`, `PerformActionUsage`, `SendActionUsage`, `AcceptActionUsage`, control nodes, `StateUsage`, `FlowUsage` and case usages.
* `BooleanExpression` also catches `ConstraintUsage`, `RequirementUsage` and invariants.
* `Function` also catches `CalculationDefinition`, `ConstraintDefinition`, `RequirementDefinition` and case definitions.
* `InvocationExpression` also catches `OperatorExpression`, `IndexExpression`, `SelectExpression`, `CollectExpression`.

Every fallback to a supertype is logged (see Logging).

# Startup checks

The scan throws if:

* a class has more than one annotation or does not extend `AbstractType`,
* the constructor `(SysML type, Mapper)` is missing,
* `core` is abstract or does not fit `C`,
* the `libraryName` does not exist in the library,
* two unrelated classes share the same key,
* the definition `D` of a library usage does not fit the definition class of its library type,
* the definition `D` of a metaclass usage is not met by any mapped definition class.

While mapping, the parser also throws, with the element name, if the definition given in the model was not mapped as `D`.

# Rules

Rules run in two stages inside `parse`:

* `GenerelRules` run before mapping, on the SysML model. They throw `IllegalArgumentException`.
* `SemanticRule` run after mapping, on the `ResultConverter`. They throw `SemanticException`.

Predefined in `DefaultRuleExecutor`:

* **MultiplicityRule:** a specialization must not violate the multiplicity of the inherited feature.
* **MultiType:** all typings of an element must be compatible with each other (except `Flow`).

## Custom rules

Extend `DefaultRuleExecutor` to keep the predefined rules, and pass the executor to `SysmlConverterMain`:

```java
public class MyExecutor extends DefaultRuleExecutor {
	@Override
	public List<SemanticRule> getSemanticRules(NewUtil newUtil) {
		return List.of(new MyRule(newUtil));
	}
}

SysmlConverterMain main = new SysmlConverterMain("MyLibrary.zip", new MyExecutor());
```

To add to the predefined general rules, call `super.getGeneralRules(newUtil)` in `getGeneralRules` and append yours. If you extend `Executor` directly, only your rules run.

# Custom mapper

`Mapper` can be extended, for example to change `idCalculation` or `isOwnedBy`. Return it from `getMapper()`:

```java
public class MyConverterMain extends SysmlConverterMain {
	public MyConverterMain() throws IOException { super("MyLibrary.zip", new MyExecutor()); }

	@Override
	protected Mapper getMapper() { return new MyMapper(scanner, newUtil); }
}
```

# Logging

Place one of these Log4j2 configurations under `src/main/resources/log4j2.xml`.

## No logs

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="Console" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{HH:mm:ss.SSS} [%t] %-5level %logger{36} - %msg%n"/>
        </Console>
    </Appenders>
    <Loggers>
        <Logger name="Mapper" level="OFF" additivity="false">
            <AppenderRef ref="Console"/>
        </Logger>
        <Root level="OFF">
            <AppenderRef ref="Console"/>
        </Root>
    </Loggers>
</Configuration>
```

## INFO (Mapper INFO, WARN and ERROR)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="Console" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{HH:mm:ss.SSS} [%t] %-5level %logger{36} - %msg%n"/>
        </Console>
    </Appenders>
    <Loggers>
        <Logger name="Mapper" level="INFO" additivity="false">
            <AppenderRef ref="Console"/>
        </Logger>
        <Root level="ERROR">
            <AppenderRef ref="Console"/>
        </Root>
    </Loggers>
</Configuration>
```

## DEBUG (Mapper DEBUG, INFO, WARN and ERROR)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="Console" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{HH:mm:ss.SSS} [%t] %-5level %logger{36} - %msg%n"/>
        </Console>
    </Appenders>
    <Loggers>
        <Logger name="Mapper" level="DEBUG" additivity="false">
            <AppenderRef ref="Console"/>
        </Logger>
        <Root level="ERROR">
            <AppenderRef ref="Console"/>
        </Root>
    </Loggers>
</Configuration>
```