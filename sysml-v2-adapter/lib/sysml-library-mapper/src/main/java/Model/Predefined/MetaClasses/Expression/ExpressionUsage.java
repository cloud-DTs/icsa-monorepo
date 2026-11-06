package Model.Predefined.MetaClasses.Expression;


import Mapper.Mapper;
import Model.Definition;
import Model.EmptyCore;
import Model.Usage;
import org.omg.sysml.lang.sysml.Expression;



public abstract class ExpressionUsage<T extends Expression> extends Usage<EmptyCore, T, Definition<?,?>> {
	protected ExpressionUsage(T sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
