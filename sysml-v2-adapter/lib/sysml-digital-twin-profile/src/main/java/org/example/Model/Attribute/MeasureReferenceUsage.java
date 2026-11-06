package org.example.Model.Attribute;

import Mapper.Mapper;
import Model.Predefined.MetaClasses.Expression.ExpressionUsage;
import Model.Predefined.MetaClasses.Expression.ReferenceUsage;
import Model.Slots;
import lombok.Getter;
import org.omg.sysml.lang.sysml.Expression;
import org.omg.sysml.lang.sysml.Feature;

import java.util.Optional;

// attribute whose value is a reference to a measure or const attribute, e.g. leftOperand = Charger1.p13.power
public abstract class MeasureReferenceUsage extends MeasureAttributeUsage<MeasureAttributeCore, MeasureAttributeDefinition<?>> {

	private static final Class<ReferenceUsage<?>> REFERENCE = Slots.rawClassOf(ReferenceUsage.class);
	private static final Class<MeasureAttributeUsage<?, ?>> MEASURE = Slots.rawClassOf(MeasureAttributeUsage.class);

	@Getter private Optional<MeasureAttributeUsage<?, ?>> reference = Optional.empty();

	protected MeasureReferenceUsage(Feature sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	@Override
	protected void mapExpression() {
		Optional<ReferenceUsage<?>> value = instance.mapOwnedElement(Expression.class, this, REFERENCE).stream().findFirst();
		expression = value.<ExpressionUsage<?>>map(referenceUsage -> referenceUsage);
		if (value.isEmpty()) return;
		if (!MEASURE.isInstance(value.get().getTarget())) {
			throw new IllegalArgumentException("'%s' has to reference a measure or const attribute, found '%s'"
					.formatted(getName(), value.get().getTarget().getName()));
		}
		reference = Optional.of(MEASURE.cast(value.get().getTarget()));
	}
}
