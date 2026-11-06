package Model.Predefined.MetaClasses.Function;


import Model.Predefined.MetaClasses.Action.ActionCore;
import Model.Predefined.MetaClasses.Action.ActionMapDefinition;
import org.omg.sysml.lang.sysml.Behavior;
import Mapper.Mapper;

public abstract class FunctionDefinition<C extends ActionCore> extends ActionMapDefinition<C> {
	protected FunctionDefinition(Behavior sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}


}
