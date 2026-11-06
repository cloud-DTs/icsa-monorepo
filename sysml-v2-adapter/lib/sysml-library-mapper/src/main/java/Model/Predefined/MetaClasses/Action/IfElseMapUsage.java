package Model.Predefined.MetaClasses.Action;

import Mapper.Mapper;
import Model.Predefined.MetaClasses.Expression.ExpressionUsage;
import Model.Slots;
import lombok.Getter;

import org.omg.sysml.lang.sysml.IfActionUsage;

import java.util.Optional;
import java.util.stream.Stream;

// template: a library maps it by a subclass annotated with @MappedMetaClass(value = IfActionUsage.class, core = EmptyActionCore.class)
public abstract class IfElseMapUsage extends ActionMapUsage<EmptyActionCore, IfActionUsage, ActionMapDefinition<EmptyActionCore>> {

	@Getter protected Optional<? extends ExpressionUsage<?>> condition = Optional.empty();
	@Getter protected Optional<? extends ActionMapUsage<?, ?, ?>> thenAction = Optional.empty();
	@Getter protected Optional<? extends ActionMapUsage<?, ?, ?>> elseAction = Optional.empty();

	public IfElseMapUsage(IfActionUsage sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	@Override
	public void fillSlots() {
		super.fillSlots();
		mapCondition();
		mapThenAction();
		mapElseAction();
	}

	protected void mapCondition() {
		condition = Slots.mapAll(instance, this, Stream.ofNullable(sysmlElement.getIfArgument()).toList(), Slots.<ExpressionUsage<?>>rawClassOf(ExpressionUsage.class)).stream().findFirst();
	}

	protected void mapThenAction() {
		thenAction = Slots.mapAll(instance, this, Stream.ofNullable(sysmlElement.getThenAction()).toList(), Slots.<ActionMapUsage<?, ?, ?>>rawClassOf(ActionMapUsage.class)).stream().findFirst();

	}

	protected void mapElseAction() {
		elseAction = Slots.mapAll(instance, this, Stream.ofNullable(sysmlElement.getElseAction()).toList(), Slots.<ActionMapUsage<?, ?, ?>>rawClassOf(ActionMapUsage.class)).stream().findFirst();

	}
}
