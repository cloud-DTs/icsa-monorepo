package org.example.Model.Twin;

import Mapper.Mapper;
import Model.AbstractType;
import org.example.Model.DTCore;
import lombok.Getter;
import org.omg.sysml.lang.sysml.Feature;
import org.omg.sysml.lang.sysml.Type;
import Model.Slots;
import org.example.Model.Attribute.TwinAttributeIntegerUsage;
import org.example.Model.Entity.EntityUsage;
import org.example.Model.Condition.ConditionUsage;
import org.example.Model.Enums.EnumLibTwinDataBaseTypeUsage;

import java.util.List;
import java.util.Optional;

// slots of DigitalTwinLibrary::LibTwin
public class TwinCore extends DTCore {

	@Getter private List<EntityUsage> entities = List.of();
	@Getter private List<ConditionUsage> conditions = List.of();
	@Getter private Optional<EnumLibTwinDataBaseTypeUsage> hotDatabaseType = Optional.empty();
	@Getter private Optional<TwinAttributeIntegerUsage> hotDatabaseRetentionDays = Optional.empty();
	@Getter private Optional<EnumLibTwinDataBaseTypeUsage> coldDataBaseType = Optional.empty();
	@Getter private Optional<TwinAttributeIntegerUsage> coldDatabaseRetentionDays = Optional.empty();

	public TwinCore(Type sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	@Override
	protected void fillDTSlots(AbstractType<?, ?> owner,List<Feature> features) {
		conditions = slot(Slots.mapAll(mapper, owner, ownFeatures(owner), ConditionUsage.class));
		entities = slot(Slots.mapAll(mapper, owner, ownFeatures(owner), EntityUsage.class));
		hotDatabaseType = Slots.atMostOne(owner, "hotDatabaseType", slot(mapper.mapSlot("hotDatabaseType", owner, EnumLibTwinDataBaseTypeUsage.class)));
		hotDatabaseRetentionDays = Slots.atMostOne(owner, "hotDatabaseRetentionDays", slot(mapper.mapSlot("hotDatabaseRetentionDays", owner, TwinAttributeIntegerUsage.class)));
		coldDataBaseType = Slots.atMostOne(owner, "coldDataBaseType", slot(mapper.mapSlot("coldDataBaseType", owner, EnumLibTwinDataBaseTypeUsage.class)));
		coldDatabaseRetentionDays = Slots.atMostOne(owner, "coldDatabaseRetentionDays", slot(mapper.mapSlot("coldDatabaseRetentionDays", owner, TwinAttributeIntegerUsage.class)));
	}

}
