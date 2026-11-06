package org.example.Model.Component;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import Model.Predefined.MetaClasses.Expression.ReferenceUsage;
import Model.Slots;
import lombok.Getter;
import org.omg.sysml.lang.sysml.Expression;
import org.omg.sysml.lang.sysml.Feature;

import java.util.Optional;

// component topic of a strategy action, its value references a component, e.g. componentTopic = Charger1.p13
@MappedLibrary(libraryName = "DigitalTwinLibrary::componentTopic", core = ComponentCore.class)
public class ComponentTopicUsage extends ComponentUsage {

	private static final Class<ReferenceUsage<?>> REFERENCE = Slots.rawClassOf(ReferenceUsage.class);

	@Getter private Optional<ComponentUsage> reference = Optional.empty();

	public ComponentTopicUsage(Feature sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	@Override
	protected void mapValue(Optional<Expression> value) {
		Optional<ReferenceUsage<?>> mapped = instance.mapOwnedElement(Expression.class, this, REFERENCE).stream().findFirst();
		if (mapped.isEmpty()) return;
		if (!ComponentUsage.class.isInstance(mapped.get().getTarget())) {
			throw new IllegalArgumentException("'%s' has to reference a component, found '%s'".formatted(getName(), mapped.get().getTarget().getName()));
		}
		reference = Optional.of(ComponentUsage.class.cast(mapped.get().getTarget()));
	}
}
