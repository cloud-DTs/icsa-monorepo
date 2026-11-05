package org.example.Model.Expression;

import Mapper.Mapper;
import Model.Annotation.MappedMetaClass;
import Model.EmptyCore;
import Model.Predefined.MetaClasses.Expression.LiteralIntegerUsage;
import org.omg.sysml.lang.sysml.LiteralInteger;

@MappedMetaClass(value = LiteralInteger.class, core = EmptyCore.class)
public class TwinLiteralIntegerUsage extends LiteralIntegerUsage {
	public TwinLiteralIntegerUsage(LiteralInteger sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
