package org.example.Model.Attribute;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import org.omg.sysml.lang.sysml.Feature;

@MappedLibrary(libraryName = "DigitalTwinLibrary::ConstAttributes", core = ConstAttributeCore.class)
public class ConstAttributeUsage extends MeasureAttributeUsage<ConstAttributeCore, ConstAttributeDefinition> implements ConstAttributeCoreApi {
	public ConstAttributeUsage(Feature sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
