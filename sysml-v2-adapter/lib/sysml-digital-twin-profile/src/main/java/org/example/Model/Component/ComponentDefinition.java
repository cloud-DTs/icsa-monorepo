package org.example.Model.Component;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import Model.Definition;
import org.omg.sysml.lang.sysml.Classifier;

@MappedLibrary(libraryName = "DigitalTwinLibrary::LibTwinComponent", core = ComponentCore.class)
public class ComponentDefinition extends Definition<ComponentCore, Classifier> implements ComponentCoreApi {
	public ComponentDefinition(Classifier sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
