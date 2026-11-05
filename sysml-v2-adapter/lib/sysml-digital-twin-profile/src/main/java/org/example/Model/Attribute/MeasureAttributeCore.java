package org.example.Model.Attribute;

import Mapper.Mapper;
import Model.AbstractType;
import Model.Slots;
import lombok.Getter;
import org.example.Model.Enums.EnumAttributeDataTypeUsage;
import org.omg.sysml.lang.sysml.Feature;
import org.omg.sysml.lang.sysml.Type;

import java.util.List;
import java.util.Optional;


public class MeasureAttributeCore extends TwinAttributeCore {

	@Getter private Optional<EnumAttributeDataTypeUsage> dataType = Optional.empty();

	public MeasureAttributeCore(Type sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	@Override
	protected void fillDTSlots(AbstractType<?, ?> owner, List<Feature> features) {
		dataType = Slots.atMostOne(owner, "dataType", slot(mapper.mapSlot("dataType", owner, EnumAttributeDataTypeUsage.class)));
	}
}
