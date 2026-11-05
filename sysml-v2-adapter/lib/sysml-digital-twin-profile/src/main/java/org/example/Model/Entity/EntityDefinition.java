package org.example.Model.Entity;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import Model.Definition;
import org.omg.sysml.lang.sysml.Classifier;

@MappedLibrary(libraryName = "DigitalTwinLibrary::LibTwinEntity", core = EntityCore.class)
public class EntityDefinition extends Definition<EntityCore, Classifier> implements EntityCoreApi {
	public EntityDefinition(Classifier sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
