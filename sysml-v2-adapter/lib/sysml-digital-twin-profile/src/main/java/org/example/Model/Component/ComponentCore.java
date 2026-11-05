package org.example.Model.Component;

import Mapper.Mapper;
import Model.AbstractType;
import lombok.Getter;
import org.example.Model.DTCore;
import org.omg.sysml.lang.sysml.Feature;
import org.omg.sysml.lang.sysml.Type;
import Model.Slots;
import org.example.Model.Attribute.ConstAttributeUsage;
import org.example.Model.Attribute.MeasureAttributeUsage;

import java.util.List;

// slots of DigitalTwinLibrary::LibTwinComponent
public class ComponentCore extends DTCore {

	private static final Class<MeasureAttributeUsage<?, ?>> MEASURE = Slots.rawClassOf(MeasureAttributeUsage.class);

	@Getter private List<MeasureAttributeUsage<?, ?>> measurements = List.of();

	public ComponentCore(Type sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	@Override
	protected void fillDTSlots(AbstractType<?, ?> owner,List<Feature> features) {
		measurements = slot(Slots.mapAll(mapper, owner, features, MEASURE).stream()
				.filter(attribute -> !ConstAttributeUsage.class.isInstance(attribute)).toList());
	}

}
