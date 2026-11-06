package org.example.Model.Attribute;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import Model.Definition;
import org.omg.sysml.lang.sysml.Classifier;

@MappedLibrary(libraryName = "Base::DataValue", core = TwinAttributeCore.class)
public class TwinAttributeDefinition<C extends TwinAttributeCore> extends Definition<C, Classifier> implements TwinAttributeCoreApi<C> {
	public TwinAttributeDefinition(Classifier sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
