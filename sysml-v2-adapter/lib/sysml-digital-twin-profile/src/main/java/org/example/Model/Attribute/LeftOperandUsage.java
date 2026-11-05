package org.example.Model.Attribute;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import org.omg.sysml.lang.sysml.Feature;

@MappedLibrary(libraryName = "DigitalTwinLibrary::leftOperand", core = MeasureAttributeCore.class)
public class LeftOperandUsage extends MeasureReferenceUsage {
	public LeftOperandUsage(Feature sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
