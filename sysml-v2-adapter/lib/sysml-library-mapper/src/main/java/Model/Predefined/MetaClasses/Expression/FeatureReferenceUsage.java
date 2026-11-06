package Model.Predefined.MetaClasses.Expression;


import Mapper.Mapper;
import Model.EmptyCore;
import Model.Usage;
import org.omg.sysml.lang.sysml.FeatureReferenceExpression;

import java.util.List;

// template: a library maps it by a subclass annotated with @MappedMetaClass(value = FeatureReferenceExpression.class, core = EmptyCore.class)
public abstract class FeatureReferenceUsage extends ReferenceUsage<FeatureReferenceExpression> {



	public FeatureReferenceUsage(FeatureReferenceExpression sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	@Override
	public void fillSlots() {
		super.fillSlots();
		mapTarget();
	}

	protected void mapTarget() {
		target = instance.mapChain(List.of(sysmlElement.getReferent()), this, Usage.class);
	}

}
