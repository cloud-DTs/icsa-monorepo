package org.example.Model.Entity;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import Model.Usage;
import org.omg.sysml.lang.sysml.Feature;

@MappedLibrary(libraryName = "DigitalTwinLibrary::LibTwinEntity", core = EntityCore.class)
public class EntityUsage extends Usage<EntityCore, Feature, EntityDefinition> implements EntityCoreApi {
	public EntityUsage(Feature sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
