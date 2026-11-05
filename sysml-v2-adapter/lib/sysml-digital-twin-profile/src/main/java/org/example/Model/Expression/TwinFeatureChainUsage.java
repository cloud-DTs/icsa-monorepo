package org.example.Model.Expression;

import Mapper.Mapper;
import Model.Annotation.MappedMetaClass;
import Model.EmptyCore;
import Model.Predefined.MetaClasses.Expression.FeatureChainUsage;
import org.omg.sysml.lang.sysml.FeatureChainExpression;

// the attribute holding the reference decides what it may point to
@MappedMetaClass(value = FeatureChainExpression.class, core = EmptyCore.class)
public class TwinFeatureChainUsage extends FeatureChainUsage {
	public TwinFeatureChainUsage(FeatureChainExpression sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}
}
