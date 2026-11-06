package Model.Predefined.MetaClasses.Function;


import Mapper.Mapper;
import Model.Predefined.MetaClasses.Action.ActionCore;
import org.omg.sysml.lang.sysml.Behavior;
import org.omg.sysml.lang.sysml.CalculationDefinition;


// template: a library maps it by a subclass annotated with @MappedMetaClass(value = CalculationDefinition.class, core = ActionCore.class)
public abstract class CustomCalculationDefinition extends FunctionDefinition<ActionCore> {
	public CustomCalculationDefinition(Behavior sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
