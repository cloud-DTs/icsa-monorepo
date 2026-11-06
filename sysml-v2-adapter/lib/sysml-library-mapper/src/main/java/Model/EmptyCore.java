package Model;

import Mapper.Mapper;
import Model.Core.Core;

import org.omg.sysml.lang.sysml.Type;

public class EmptyCore extends Core<Type> {

	public EmptyCore(Type sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	@Override
	public void fillSlots(AbstractType<?,?> owner) {
	}
}
