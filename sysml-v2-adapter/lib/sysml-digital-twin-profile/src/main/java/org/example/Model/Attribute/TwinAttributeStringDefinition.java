package org.example.Model.Attribute;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import org.omg.sysml.lang.sysml.Classifier;

@MappedLibrary(libraryName = "ScalarValues::String", core = TwinAttributeCore.class)
public class TwinAttributeStringDefinition extends TwinAttributeDefinition<TwinAttributeCore> {
	public TwinAttributeStringDefinition(Classifier sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
