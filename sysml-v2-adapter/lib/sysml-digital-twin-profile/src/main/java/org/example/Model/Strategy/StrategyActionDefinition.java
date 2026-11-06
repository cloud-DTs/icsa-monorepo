package org.example.Model.Strategy;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import Model.Definition;
import org.omg.sysml.lang.sysml.Classifier;

@MappedLibrary(libraryName = "DigitalTwinLibrary::LibTwinStrategyAction", core = StrategyActionCore.class)
public class StrategyActionDefinition extends Definition<StrategyActionCore, Classifier> implements StrategyActionCoreApi {
	public StrategyActionDefinition(Classifier sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
