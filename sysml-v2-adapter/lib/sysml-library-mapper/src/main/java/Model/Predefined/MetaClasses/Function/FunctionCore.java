package Model.Predefined.MetaClasses.Function;

import Mapper.Mapper;
import Model.AbstractType;
import Model.Predefined.MetaClasses.Action.ActionCore;
import lombok.Getter;

import org.omg.sysml.lang.sysml.Type;


public class FunctionCore extends ActionCore {

	@Getter
	protected FunctionKind functionKind;

	public FunctionCore(Type sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);

	}

	@Override
	public void fillSlots(AbstractType<?,?> owner) {
		mapFunctionKind();
	}

	protected void mapFunctionKind() {
		functionKind = BaseFunctionKind.fromSymbol(sysmlElement.getName());
	}
}
