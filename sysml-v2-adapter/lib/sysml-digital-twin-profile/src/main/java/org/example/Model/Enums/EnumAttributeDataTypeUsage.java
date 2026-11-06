package org.example.Model.Enums;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import Model.EmptyCore;
import org.omg.sysml.lang.sysml.Feature;

@MappedLibrary(libraryName = "DigitalTwinLibrary::AttributeDataType", core = EmptyCore.class)
public class EnumAttributeDataTypeUsage extends EnumAttributeUsage<EnumAttributeDataType> {
	public EnumAttributeDataTypeUsage(Feature sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	@Override
	protected Class<EnumAttributeDataType> getEnumClass() {
		return EnumAttributeDataType.class;
	}
}
