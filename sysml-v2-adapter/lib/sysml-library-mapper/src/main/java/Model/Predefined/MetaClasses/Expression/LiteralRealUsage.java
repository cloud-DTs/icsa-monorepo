package Model.Predefined.MetaClasses.Expression;


import Mapper.Mapper;
import Model.EmptyCore;
import org.omg.sysml.lang.sysml.LiteralBoolean;
import org.omg.sysml.lang.sysml.LiteralRational;
// template: a library maps it by a subclass annotated with @MappedMetaClass(value = LiteralRational.class, core = EmptyCore.class)
public abstract class LiteralRealUsage extends LiteralUsage<Double> {
	public LiteralRealUsage(LiteralRational sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
		this.value = sysmlElement.getValue();
	}
}
