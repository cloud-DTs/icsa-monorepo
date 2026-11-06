package org.example.Model.Expression;

import Mapper.Mapper;
import Model.Annotation.MappedMetaClass;
import Model.EmptyCore;
import Model.Predefined.MetaClasses.Expression.LiteralStringUsage;
import org.omg.sysml.lang.sysml.LiteralString;

@MappedMetaClass(value = LiteralString.class, core = EmptyCore.class)
public class TwinLiteralStringUsage extends LiteralStringUsage {
	public TwinLiteralStringUsage(LiteralString sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
