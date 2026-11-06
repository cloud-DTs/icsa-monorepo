package Model.Predefined.MetaClasses.Function;


import Mapper.Mapper;
import org.omg.sysml.lang.sysml.Behavior;
import org.omg.sysml.lang.sysml.Function;


// template: a library maps it by a subclass annotated with @MappedMetaClass(value = Function.class, core = FunctionCore.class)
public abstract class BaseFunctionDefinition extends FunctionDefinition<FunctionCore> {
	public BaseFunctionDefinition(Behavior sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
