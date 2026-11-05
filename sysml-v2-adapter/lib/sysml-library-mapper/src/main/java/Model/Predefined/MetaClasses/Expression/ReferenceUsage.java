package Model.Predefined.MetaClasses.Expression;

import Mapper.Mapper;
import Model.Usage;
import lombok.Getter;

import org.omg.sysml.lang.sysml.Expression;

public abstract class ReferenceUsage<T extends Expression> extends ExpressionUsage<T> {

	@Getter
	protected Usage<?, ?, ?> target;

	protected ReferenceUsage(T sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
