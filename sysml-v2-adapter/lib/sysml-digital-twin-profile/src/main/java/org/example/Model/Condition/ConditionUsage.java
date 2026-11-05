package org.example.Model.Condition;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import Model.Usage;
import org.omg.sysml.lang.sysml.Feature;

@MappedLibrary(libraryName = "DigitalTwinLibrary::LibTwinConditionAction", core = ConditionCore.class)
public class ConditionUsage extends Usage<ConditionCore, Feature, ConditionDefinition> implements ConditionCoreApi {
	public ConditionUsage(Feature sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
