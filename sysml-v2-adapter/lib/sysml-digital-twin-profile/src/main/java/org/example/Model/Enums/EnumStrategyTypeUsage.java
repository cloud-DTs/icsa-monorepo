package org.example.Model.Enums;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import Model.EmptyCore;
import org.omg.sysml.lang.sysml.Feature;

@MappedLibrary(libraryName = "DigitalTwinLibrary::StrategyType", core = EmptyCore.class)
public class EnumStrategyTypeUsage extends EnumAttributeUsage<EnumStrategyType> {
	public EnumStrategyTypeUsage(Feature sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	@Override
	protected Class<EnumStrategyType> getEnumClass() {
		return EnumStrategyType.class;
	}
}
