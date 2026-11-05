package org.example.Model.Attribute;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import org.omg.sysml.lang.sysml.Classifier;

@MappedLibrary(libraryName = "DigitalTwinLibrary::ConstAttributes", core = ConstAttributeCore.class)
public class ConstAttributeDefinition extends MeasureAttributeDefinition<ConstAttributeCore> implements ConstAttributeCoreApi {
	public ConstAttributeDefinition(Classifier sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
