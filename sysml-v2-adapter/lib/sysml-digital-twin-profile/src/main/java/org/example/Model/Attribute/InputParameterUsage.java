package org.example.Model.Attribute;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import org.omg.sysml.lang.sysml.Feature;

@MappedLibrary(libraryName = "DigitalTwinLibrary::inputParameters", core = MeasureAttributeCore.class)
public class InputParameterUsage extends MeasureReferenceUsage {
	public InputParameterUsage(Feature sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
