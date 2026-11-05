package org.example.Model.Attribute;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import org.omg.sysml.lang.sysml.Feature;

@MappedLibrary(libraryName = "ScalarValues::Boolean", core = TwinAttributeCore.class)
public class TwinAttributeBooleanUsage extends TwinAttributeUsage<TwinAttributeCore, TwinAttributeBooleanDefinition> {
	public TwinAttributeBooleanUsage(Feature sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
