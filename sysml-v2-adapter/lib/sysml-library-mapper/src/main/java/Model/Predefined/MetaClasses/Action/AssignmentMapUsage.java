package Model.Predefined.MetaClasses.Action;

import Mapper.Mapper;
import Model.Predefined.MetaClasses.Expression.ExpressionUsage;
import Model.Slots;
import Model.Usage;
import lombok.Getter;
import org.omg.sysml.lang.sysml.*;


import java.util.ArrayList;
import java.util.List;

// template: a library maps it by a subclass annotated with @MappedMetaClass(value = AssignmentActionUsage.class, core = EmptyActionCore.class)
public abstract class AssignmentMapUsage extends ActionMapUsage<EmptyActionCore,AssignmentActionUsage,ActionMapDefinition<EmptyActionCore>> {

	@Getter
	protected Usage<?, ?, ?> referent;
	@Getter
	protected ExpressionUsage<?> value;

	public AssignmentMapUsage(AssignmentActionUsage sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	@Override
	public void fillSlots() {
		super.fillSlots();
		mapReferent();
		mapValue();

	}


	// chain from the assignment target to the assigned feature
	protected List<Feature> referentChain() {
		Expression ta = sysmlElement.getTargetArgument();
		List<Feature> chain = new ArrayList<>();
		if (ta instanceof FeatureReferenceExpression r) {
			chain.add(r.getReferent());
		} else if (ta instanceof FeatureChainExpression c) {
			if (c.getArgument().getFirst() instanceof FeatureReferenceExpression base) {
				chain.add(base.getReferent());
			}
			Feature t = c.getTargetFeature();
			chain.addAll(t.getChainingFeature().isEmpty() ? List.of(t) : t.getChainingFeature());
		}
		Feature ref = sysmlElement.getReferent();
		chain.addAll(ref.getChainingFeature().isEmpty() ? List.of(ref) : ref.getChainingFeature());
		return chain;
	}

	protected void mapReferent() {
		referent = instance.mapChain(referentChain(), this, Usage.class);
	}

	protected void mapValue()
	{
		value = Slots.mapAll(instance, this, List.of(sysmlElement.getValueExpression()), ExpressionUsage.class).getFirst();

	}
}
