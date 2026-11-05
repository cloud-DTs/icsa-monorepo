package Model.Predefined.MetaClasses.Action;

import Mapper.Mapper;
import Model.Predefined.MetaClasses.Expression.ExpressionUsage;
import Model.Slots;
import lombok.Getter;

import org.omg.sysml.lang.sysml.TransitionUsage;

import java.util.List;
import java.util.Optional;


// template: a library maps it by a subclass annotated with @MappedMetaClass(value = TransitionUsage.class, core = EmptyActionCore.class)
public abstract class TransitionMapUsage extends ActionMapUsage<EmptyActionCore, TransitionUsage, ActionMapDefinition<EmptyActionCore>> {

	@Getter protected List<? extends ExpressionUsage<?>> guard = List.of();
	@Getter protected Optional<? extends ActionMapUsage<?, ?, ?>> effectAction = Optional.empty();
	@Getter protected ActionMapUsage<?, ?, ?> source;
	@Getter protected ActionMapUsage<?, ?, ?> target;


	public TransitionMapUsage(TransitionUsage sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	@Override
	public void fillSlots() {
		super.fillSlots();
		mapGuard();
		mapEffectAction();
		mapSource();
		mapTarget();
	}



	protected void mapGuard() {
		guard = Slots.mapAll(instance, this, sysmlElement.getGuardExpression(), Slots.<ExpressionUsage<?>>rawClassOf(ExpressionUsage.class));
	}
	protected void mapEffectAction() {
		effectAction = Slots.atMostOne(this, "effectAction", Slots.mapAll(instance, this, sysmlElement.getEffectAction(),
				Slots.<ActionMapUsage<?, ?, ?>>rawClassOf(ActionMapUsage.class)));
	}

	protected void mapSource() {
		source = instance.mapChain(List.of(sysmlElement.getSource()), this, ActionMapUsage.class);
	}

	protected  void mapTarget() {
		target = instance.mapChain(List.of(sysmlElement.getTarget()), this, ActionMapUsage.class);
	}

}
