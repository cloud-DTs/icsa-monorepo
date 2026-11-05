package Model.Predefined.MetaClasses.Expression;

import Mapper.Mapper;
import Model.EmptyCore;
import Model.Predefined.MetaClasses.Function.FunctionDefinition;
import lombok.Getter;

import org.omg.sysml.lang.sysml.InvocationExpression;

// template: a library maps it by a subclass annotated with @MappedMetaClass(value = InvocationExpression.class, core = EmptyCore.class)
public abstract class CalculationUsage extends InvocationUsage<InvocationExpression> {

	@Getter protected FunctionDefinition<?> invokeType;

	public CalculationUsage(InvocationExpression sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	@Override
	public void fillSlots() {
		super.fillSlots();
		mapInvokedType();
	}


	protected void mapInvokedType() {
		invokeType = instance.map(sysmlElement.getInstantiatedType(), null, FunctionDefinition.class);
	}
}
