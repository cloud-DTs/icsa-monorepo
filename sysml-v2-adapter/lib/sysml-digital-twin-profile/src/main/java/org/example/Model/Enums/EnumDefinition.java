package org.example.Model.Enums;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import Model.Definition;
import Model.EmptyCore;
import org.omg.sysml.lang.sysml.Classifier;

@MappedLibrary(libraryName = "DigitalTwinLibrary::TwinEnum", core = EmptyCore.class)
public class EnumDefinition extends Definition<EmptyCore, Classifier> {
	public EnumDefinition(Classifier sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
