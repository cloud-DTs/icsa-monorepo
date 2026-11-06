package org.example.Model.Twin;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import Model.Definition;
import org.omg.sysml.lang.sysml.Classifier;

@MappedLibrary(libraryName = "DigitalTwinLibrary::LibTwin", core = TwinCore.class)
public class TwinDefinition extends Definition<TwinCore, Classifier> implements TwinCoreApi {
	public TwinDefinition(Classifier sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
