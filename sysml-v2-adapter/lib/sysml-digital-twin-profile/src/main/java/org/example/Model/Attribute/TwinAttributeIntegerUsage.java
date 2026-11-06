package org.example.Model.Attribute;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import org.omg.sysml.lang.sysml.Feature;

@MappedLibrary(libraryName = "ScalarValues::Integer", core = TwinAttributeCore.class)
public class TwinAttributeIntegerUsage extends TwinAttributeUsage<TwinAttributeCore, TwinAttributeIntegerDefinition> {
	public TwinAttributeIntegerUsage(Feature sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
