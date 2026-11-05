package org.example.Model.Attribute;

import Mapper.Mapper;
import Model.AbstractType;
import Model.Slots;
import lombok.Getter;
import org.omg.sysml.lang.sysml.Feature;
import org.omg.sysml.lang.sysml.Type;

import java.util.List;
import java.util.Optional;

// slots of DigitalTwinLibrary::ConstAttributes, which specializes LibDTAttributes
public class ConstAttributeCore extends MeasureAttributeCore {

	@Getter private Optional<TwinAttributeStringUsage> value = Optional.empty();

	public ConstAttributeCore(Type sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	@Override
	protected void fillDTSlots(AbstractType<?, ?> owner, List<Feature> features) {
		super.fillDTSlots(owner, features);
		value = Slots.atMostOne(owner, "value", slot(mapper.mapSlot("value", owner, TwinAttributeStringUsage.class)));
	}
}
