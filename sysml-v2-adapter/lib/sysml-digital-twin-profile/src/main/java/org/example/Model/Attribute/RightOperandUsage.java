package org.example.Model.Attribute;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import org.omg.sysml.lang.sysml.Feature;

@MappedLibrary(libraryName = "DigitalTwinLibrary::rightOperand", core = MeasureAttributeCore.class)
public class RightOperandUsage extends MeasureReferenceUsage {
	public RightOperandUsage(Feature sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
