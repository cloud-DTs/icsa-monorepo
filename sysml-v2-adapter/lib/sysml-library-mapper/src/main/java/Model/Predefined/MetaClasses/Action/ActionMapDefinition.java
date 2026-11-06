package Model.Predefined.MetaClasses.Action;

import Mapper.Mapper;
import Model.Definition;
import org.omg.sysml.lang.sysml.Behavior;

public abstract class ActionMapDefinition<C extends ActionCore> extends Definition<C, Behavior> implements ActionCoreApi<C>{
	protected ActionMapDefinition(Behavior sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

}