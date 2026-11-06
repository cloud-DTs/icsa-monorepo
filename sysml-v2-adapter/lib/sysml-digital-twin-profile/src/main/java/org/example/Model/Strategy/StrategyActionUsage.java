package org.example.Model.Strategy;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import Model.Usage;
import org.omg.sysml.lang.sysml.Feature;

@MappedLibrary(libraryName = "DigitalTwinLibrary::LibTwinStrategyAction", core = StrategyActionCore.class)
public class StrategyActionUsage extends Usage<StrategyActionCore, Feature, StrategyActionDefinition> implements StrategyActionCoreApi {
	public StrategyActionUsage(Feature sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
