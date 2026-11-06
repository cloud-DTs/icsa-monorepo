package org.example.Model.Attribute;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import org.omg.sysml.lang.sysml.Classifier;

@MappedLibrary(libraryName = "ScalarValues::Boolean", core = TwinAttributeCore.class)
public class TwinAttributeBooleanDefinition extends TwinAttributeDefinition<TwinAttributeCore> {
	public TwinAttributeBooleanDefinition(Classifier sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
