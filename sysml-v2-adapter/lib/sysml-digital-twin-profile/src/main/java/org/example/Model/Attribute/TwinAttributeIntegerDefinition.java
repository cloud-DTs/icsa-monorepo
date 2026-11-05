package org.example.Model.Attribute;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import org.omg.sysml.lang.sysml.Classifier;

@MappedLibrary(libraryName = "ScalarValues::Integer", core = TwinAttributeCore.class)
public class TwinAttributeIntegerDefinition extends TwinAttributeDefinition<TwinAttributeCore> {
	public TwinAttributeIntegerDefinition(Classifier sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
