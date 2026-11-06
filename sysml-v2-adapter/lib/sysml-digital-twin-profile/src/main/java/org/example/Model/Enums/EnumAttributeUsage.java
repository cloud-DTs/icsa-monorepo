package org.example.Model.Enums;

import Mapper.Mapper;
import Model.EmptyCore;
import Model.Usage;
import lombok.Getter;
import org.omg.sysml.lang.sysml.EnumerationUsage;
import org.omg.sysml.lang.sysml.Expression;
import org.omg.sysml.lang.sysml.Feature;
import org.omg.sysml.lang.sysml.FeatureReferenceExpression;
import org.omg.sysml.lang.sysml.FeatureValue;

import java.util.Arrays;
import java.util.Optional;

/** Attribute typed by a library enum; the value is the referenced enum literal. */
public abstract class EnumAttributeUsage<E extends Enum<E> & TwinEnum> extends Usage<EmptyCore, Feature, EnumDefinition> {

	@Getter private Optional<E> value = Optional.empty();

	protected EnumAttributeUsage(Feature sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	protected abstract Class<E> getEnumClass();

	@Override
	public void fillSlots() {
		super.fillSlots();
		Optional<Expression> expression = sysmlElement.getOwnedMembership().stream().filter(FeatureValue.class::isInstance)
				.map(FeatureValue.class::cast).map(FeatureValue::getValue).findFirst();
		if (expression.isEmpty()) return;

		// the value has to be exactly one enum literal, nothing else is skipped silently
		if (!FeatureReferenceExpression.class.isInstance(expression.get())
				|| !EnumerationUsage.class.isInstance(FeatureReferenceExpression.class.cast(expression.get()).getReferent())) {
			throw new IllegalStateException("Enum attribute '%s' must have exactly one enum value".formatted(getName()));
		}
		String symbol = FeatureReferenceExpression.class.cast(expression.get()).getReferent().getName();
		value = Optional.of(Arrays.stream(getEnumClass().getEnumConstants()).filter(e -> e.getStringRepresentation().equals(symbol)).findFirst()
				.orElseThrow(() -> new IllegalStateException("'%s' is not a valid value of %s".formatted(symbol, getEnumClass().getSimpleName()))));
	}
}
