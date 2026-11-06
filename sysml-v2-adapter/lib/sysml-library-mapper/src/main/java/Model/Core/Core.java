package Model.Core;


import Mapper.Mapper;
import Model.AbstractType;
import org.omg.sysml.lang.sysml.Type;

public abstract class Core<T extends Type> {

	protected T sysmlElement;
	protected Mapper mapper;

	public Core(T sysmlElement, Mapper mapper) {
		this.sysmlElement = sysmlElement; this.mapper = mapper;
	}

	public abstract void fillSlots(AbstractType<?,?> owner);

}

