package org.example.Model.Attribute;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import org.omg.sysml.lang.sysml.Feature;

@MappedLibrary(libraryName = "DigitalTwinLibrary::LibDTAttributes", core = MeasureAttributeCore.class)
public class MeasureAttributeUsage<C extends MeasureAttributeCore, D extends MeasureAttributeDefinition<?>> extends TwinAttributeUsage<C, D> implements MeasureAttributeCoreApi<C> {
	public MeasureAttributeUsage(Feature sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
