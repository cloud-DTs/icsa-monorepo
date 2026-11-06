package Model.Predefined.MetaClasses.Expression;


import Mapper.Mapper;
import Model.EmptyCore;
import org.omg.sysml.lang.sysml.LiteralBoolean;
import org.omg.sysml.lang.sysml.LiteralInteger;
// template: a library maps it by a subclass annotated with @MappedMetaClass(value = LiteralInteger.class, core = EmptyCore.class)
public abstract class LiteralIntegerUsage extends LiteralUsage<Integer> {
	public LiteralIntegerUsage(LiteralInteger sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
		this.value = sysmlElement.getValue();
	}
}
