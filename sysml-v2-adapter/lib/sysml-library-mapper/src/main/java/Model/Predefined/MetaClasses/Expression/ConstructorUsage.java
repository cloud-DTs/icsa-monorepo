package Model.Predefined.MetaClasses.Expression;

import Mapper.Mapper;
import Model.EmptyCore;
import Model.Definition;
import lombok.Getter;
import org.omg.sysml.lang.sysml.ConstructorExpression;


// template: a library maps it by a subclass annotated with @MappedMetaClass(value = ConstructorExpression.class, core = EmptyCore.class)
public abstract class ConstructorUsage extends InvocationUsage<ConstructorExpression> {

	@Getter protected Definition<?,?> constructorType;

	public ConstructorUsage(ConstructorExpression sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	@Override
	public void fillSlots() {
		super.fillSlots();
		mapConstructorType();
	}

	protected void mapConstructorType() {
		constructorType = instance.map(sysmlElement.getInstantiatedType(), null, Definition.class);
	}


}
