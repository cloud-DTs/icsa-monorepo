package SourceService.SourceXMIElements.Mapper;

import java.util.Arrays;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

public enum Stereotypes {
    COMPONENT("Component"),
    DEVICE("Device"),
    STRATEGY("Strategy"),
    DATABASE("DataBase"),
    TWIN("Twin"),



    COMPONENT_INSTANCE("ComponentInstance"),
    DEVICE_INSTANCE("DeviceInstance"),
    STRATEGY_INSTANCE("StrategyInstance"),
    DATABASE_INSTANCE("DataBaseInstance"),
    CONST_INSTANCE("ConstInstance"),
    MEASUREMENT_INSTANCE("MeasurementInstance"),


    HAS_COMPONENT("hasComponent"),
    HAS_DEVICE("hasDevice"),
    HAS_STRATEGY("hasStrategy"),
    SENDS_TO("sendsTo"),
    MEASURES("measures"),
    TRIGGERS("triggers"),
    FEEDBACK_TOPIC("feedbackTopic"),


    TWIN_INSTANCE("TwinInstance");

    private final String label;

    Stereotypes(String label) {
        this.label = label;
    }

    public String getLabel() {
        return label;
    }

    private static final Map<String, Stereotypes> MAP = Arrays.stream(values())
            .collect(Collectors.toMap(Stereotypes::getLabel, Function.identity()));

    public static Stereotypes typeByName(String name) {
        return MAP.get(name);
    }



    @Override
    public String toString() {
        return label;
    }
}
