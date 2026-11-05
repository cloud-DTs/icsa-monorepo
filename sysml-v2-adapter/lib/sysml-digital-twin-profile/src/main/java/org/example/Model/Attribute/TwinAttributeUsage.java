package org.example.Model.Attribute;

import Mapper.Mapper;
import Model.Annotation.MappedLibrary;
import Model.Predefined.MetaClasses.Expression.ExpressionUsage;
import Model.Predefined.MetaClasses.Expression.LiteralUsage;
import Model.Slots;
import Model.Usage;
import lombok.Getter;
import org.omg.sysml.lang.sysml.Expression;
import org.omg.sysml.lang.sysml.Feature;

import java.util.Optional;

@MappedLibrary(libraryName = "Base::DataValue", core = TwinAttributeCore.class)
public class TwinAttributeUsage<C extends TwinAttributeCore, D extends TwinAttributeDefinition<?>> extends Usage<C, Feature, D> implements TwinAttributeCoreApi<C> {

	private static final Class<LiteralUsage<?>> LITERAL = Slots.rawClassOf(LiteralUsage.class);

	@Getter protected Optional<ExpressionUsage<?>> expression = Optional.empty();

	public TwinAttributeUsage(Feature sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	@Override
	public void fillSlots() {
		super.fillSlots();
		mapExpression();
	}

	protected void mapExpression() {
		expression = instance.mapOwnedElement(Expression.class, this, LITERAL).stream().findFirst().<ExpressionUsage<?>>map(literal -> literal);
	}
}
