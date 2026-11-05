package org.example.Model.Condition;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import Model.Definition;
import org.omg.sysml.lang.sysml.Classifier;

@MappedLibrary(libraryName = "DigitalTwinLibrary::LibTwinConditionAction", core = ConditionCore.class)
public class ConditionDefinition extends Definition<ConditionCore, Classifier> implements ConditionCoreApi {
	public ConditionDefinition(Classifier sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
