package Model.Predefined.MetaClasses.Expression;

import Mapper.Mapper;
import Model.Annotation.MappedMetaClass;
import Model.Slots;
import lombok.Getter;

import org.omg.sysml.lang.sysml.InstantiationExpression;

import java.util.List;


public abstract class InvocationUsage<U extends InstantiationExpression> extends ExpressionUsage<U> {

	@Getter protected List<? extends ExpressionUsage<?>> arguments = List.of();

	protected InvocationUsage(U sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	@Override
	public void fillSlots() {
		super.fillSlots();
		mapArguments();
	}

	protected void mapArguments() {
		arguments = Slots.mapAll(instance, this, sysmlElement.getArgument(), Slots.rawClassOf(ExpressionUsage.class));
	}


}
