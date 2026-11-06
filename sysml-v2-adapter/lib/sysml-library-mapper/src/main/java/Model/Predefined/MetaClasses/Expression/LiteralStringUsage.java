package Model.Predefined.MetaClasses.Expression;


import Mapper.Mapper;
import Model.EmptyCore;
import org.omg.sysml.lang.sysml.LiteralBoolean;
import org.omg.sysml.lang.sysml.LiteralString;
// template: a library maps it by a subclass annotated with @MappedMetaClass(value = LiteralString.class, core = EmptyCore.class)
public abstract class LiteralStringUsage extends LiteralUsage<String> {
	public LiteralStringUsage(LiteralString sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
		this.value = sysmlElement.getValue();
	}
}
