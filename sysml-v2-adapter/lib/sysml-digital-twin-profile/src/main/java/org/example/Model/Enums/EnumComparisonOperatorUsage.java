package org.example.Model.Enums;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import Model.EmptyCore;
import org.omg.sysml.lang.sysml.Feature;

@MappedLibrary(libraryName = "DigitalTwinLibrary::ComparisonOperator", core = EmptyCore.class)
public class EnumComparisonOperatorUsage extends EnumAttributeUsage<EnumComparisonOperator> {
	public EnumComparisonOperatorUsage(Feature sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	@Override
	protected Class<EnumComparisonOperator> getEnumClass() {
		return EnumComparisonOperator.class;
	}
}
