package Model.Predefined.MetaClasses.Action;

import Mapper.Mapper;
import Model.Usage;
import org.omg.sysml.lang.sysml.ActionUsage;

public abstract class ActionMapUsage <C extends ActionCore, U extends ActionUsage, D extends ActionMapDefinition<?>> extends Usage<C, U, D> implements ActionCoreApi<C> {
	protected ActionMapUsage(U sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
