package org.example.Model.Entity;

import Mapper.Mapper;
import Model.AbstractType;
import lombok.Getter;
import org.example.Model.DTCore;
import Model.Slots;
import org.omg.sysml.lang.sysml.Feature;
import org.omg.sysml.lang.sysml.Type;
import org.example.Model.Attribute.ConstAttributeUsage;
import org.example.Model.Component.ComponentUsage;
import org.example.Model.Condition.ConditionUsage;

import java.util.List;

// slots of DigitalTwinLibrary::LibTwinEntity
public class EntityCore extends DTCore {

	@Getter private List<ConstAttributeUsage> constAttributes = List.of();
	@Getter private List<EntityUsage> entities = List.of();
	@Getter private List<ComponentUsage> components = List.of();
	@Getter private List<ConditionUsage> strategies = List.of();

	public EntityCore(Type sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	@Override
	protected void fillDTSlots(AbstractType<?, ?> owner,List<Feature> features) {
		constAttributes = slot(Slots.mapAll(mapper, owner, features, ConstAttributeUsage.class));
		entities = slot(Slots.mapAll(mapper, owner, features, EntityUsage.class));
		components = slot(Slots.mapAll(mapper, owner, features, ComponentUsage.class));
		strategies = slot(Slots.mapAll(mapper, owner, features, ConditionUsage.class));
	}

}
