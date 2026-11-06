package org.example.Model.Component;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import Model.Usage;
import org.omg.sysml.lang.sysml.Expression;
import org.omg.sysml.lang.sysml.Feature;
import org.omg.sysml.lang.sysml.FeatureValue;

import java.util.Optional;

@MappedLibrary(libraryName = "DigitalTwinLibrary::LibTwinComponent", core = ComponentCore.class)
public class ComponentUsage extends Usage<ComponentCore, Feature, ComponentDefinition> implements ComponentCoreApi {

	public ComponentUsage(Feature sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	@Override
	public void fillSlots() {
		super.fillSlots();
		mapValue(sysmlElement.getOwnedMembership().stream().filter(FeatureValue.class::isInstance)
				.map(FeatureValue.class::cast).map(FeatureValue::getValue).findFirst());
	}

	// a component has no value; the component topic overrides this
	protected void mapValue(Optional<Expression> value) {
		if (value.isPresent()) {
			throw new IllegalArgumentException("Component '%s' cannot have a value".formatted(getName()));
		}
	}
}
