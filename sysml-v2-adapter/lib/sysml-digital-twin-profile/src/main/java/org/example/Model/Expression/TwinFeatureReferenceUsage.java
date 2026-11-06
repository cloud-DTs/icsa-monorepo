package org.example.Model.Expression;

import Mapper.Mapper;
import Model.Annotation.MappedMetaClass;
import Model.EmptyCore;
import Model.Predefined.MetaClasses.Expression.FeatureReferenceUsage;
import org.omg.sysml.lang.sysml.FeatureReferenceExpression;

// the attribute holding the reference decides what it may point to
@MappedMetaClass(value = FeatureReferenceExpression.class, core = EmptyCore.class)
public class TwinFeatureReferenceUsage extends FeatureReferenceUsage {
	public TwinFeatureReferenceUsage(FeatureReferenceExpression sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
