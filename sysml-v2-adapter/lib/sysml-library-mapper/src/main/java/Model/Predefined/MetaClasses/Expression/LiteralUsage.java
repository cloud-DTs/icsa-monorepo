package Model.Predefined.MetaClasses.Expression;

import Mapper.Mapper;
import lombok.Getter;
import org.omg.sysml.lang.sysml.LiteralExpression;

public abstract class LiteralUsage<V> extends ExpressionUsage<LiteralExpression> {

	@Getter protected V value;
	protected LiteralUsage(LiteralExpression sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
