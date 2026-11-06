package org.example.Model.Attribute;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import org.omg.sysml.lang.sysml.Classifier;

@MappedLibrary(libraryName = "DigitalTwinLibrary::LibDTAttributes", core = MeasureAttributeCore.class)
public class MeasureAttributeDefinition<C extends MeasureAttributeCore> extends TwinAttributeDefinition<C> implements MeasureAttributeCoreApi<C> {
	public MeasureAttributeDefinition(Classifier sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
