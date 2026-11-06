package org.example.Model.Enums;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import Model.EmptyCore;
import org.omg.sysml.lang.sysml.Feature;

@MappedLibrary(libraryName = "DigitalTwinLibrary::LibTwinDataBaseType", core = EmptyCore.class)
public class EnumLibTwinDataBaseTypeUsage extends EnumAttributeUsage<EnumLibTwinDataBaseType> {
	public EnumLibTwinDataBaseTypeUsage(Feature sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	@Override
	protected Class<EnumLibTwinDataBaseType> getEnumClass() {
		return EnumLibTwinDataBaseType.class;
	}
}
