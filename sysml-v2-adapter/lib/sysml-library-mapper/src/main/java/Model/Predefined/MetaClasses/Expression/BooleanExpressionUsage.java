package Model.Predefined.MetaClasses.Expression;


import Mapper.Mapper;
import Model.EmptyCore;
import org.omg.sysml.lang.sysml.BooleanExpression;
// template: a library maps it by a subclass annotated with @MappedMetaClass(value = BooleanExpression.class, core = EmptyCore.class)
public abstract class BooleanExpressionUsage extends ExpressionUsage<BooleanExpression> {
	public BooleanExpressionUsage(BooleanExpression sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
