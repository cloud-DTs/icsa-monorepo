package Model.Predefined.MetaClasses.Expression;


import Mapper.Mapper;
import Model.EmptyCore;
import org.omg.sysml.lang.sysml.LiteralBoolean;

// template: a library maps it by a subclass annotated with @MappedMetaClass(value = LiteralBoolean.class, core = EmptyCore.class)
public abstract class LiteralBooleanUsage extends LiteralUsage<Boolean> {
	public LiteralBooleanUsage(LiteralBoolean sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
		this.value = sysmlElement.isValue();
	}



}
