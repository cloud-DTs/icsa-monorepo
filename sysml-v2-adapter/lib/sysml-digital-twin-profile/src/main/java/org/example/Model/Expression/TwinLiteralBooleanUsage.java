package org.example.Model.Expression;

import Mapper.Mapper;
import Model.Annotation.MappedMetaClass;
import Model.EmptyCore;
import Model.Predefined.MetaClasses.Expression.LiteralBooleanUsage;
import org.omg.sysml.lang.sysml.LiteralBoolean;

@MappedMetaClass(value = LiteralBoolean.class, core = EmptyCore.class)
public class TwinLiteralBooleanUsage extends LiteralBooleanUsage {
	public TwinLiteralBooleanUsage(LiteralBoolean sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
