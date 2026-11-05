package org.example.Model.Attribute;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import org.omg.sysml.lang.sysml.Feature;

@MappedLibrary(libraryName = "DigitalTwinLibrary::outputParameters", core = MeasureAttributeCore.class)
public class OutputParameterUsage extends MeasureReferenceUsage {
	public OutputParameterUsage(Feature sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
