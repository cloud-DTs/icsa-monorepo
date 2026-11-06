package Model.Predefined.MetaClasses.Expression;

import Mapper.Mapper;
import Model.EmptyCore;
import Model.Usage;
import org.omg.sysml.lang.sysml.Feature;
import org.omg.sysml.lang.sysml.FeatureChainExpression;
import org.omg.sysml.lang.sysml.FeatureReferenceExpression;

import java.util.ArrayList;
import java.util.List;

// template: a library maps it by a subclass annotated with @MappedMetaClass(value = FeatureChainExpression.class, core = EmptyCore.class)
public abstract class FeatureChainUsage extends ReferenceUsage<FeatureChainExpression> {



	public FeatureChainUsage(FeatureChainExpression sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	@Override
	public void fillSlots() {
		super.fillSlots();
		mapTarget();
	}

	protected void mapTarget(){
		List<Feature> chain = new ArrayList<>();
		if (sysmlElement.getArgument().getFirst() instanceof FeatureReferenceExpression base){
			chain.add(base.getReferent());
		}
		Feature t = sysmlElement.getTargetFeature();
		chain.addAll(t.getChainingFeature().isEmpty() ? List.of(t) : t.getChainingFeature());
		target = instance.mapChain(chain, this, Usage.class);
	}


}
