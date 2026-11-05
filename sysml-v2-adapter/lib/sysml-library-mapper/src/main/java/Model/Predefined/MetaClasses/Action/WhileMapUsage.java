package Model.Predefined.MetaClasses.Action;

import Mapper.Mapper;
import Model.Predefined.MetaClasses.Expression.ExpressionUsage;
import Model.Slots;
import lombok.Getter;
import org.omg.sysml.lang.sysml.WhileLoopActionUsage;

import java.util.Optional;
import java.util.stream.Stream;

// template: a library maps it by a subclass annotated with @MappedMetaClass(value = WhileLoopActionUsage.class, core = EmptyActionCore.class)
public abstract class WhileMapUsage extends ActionMapUsage<EmptyActionCore, WhileLoopActionUsage, ActionMapDefinition<EmptyActionCore>> {

	@Getter protected Optional<? extends ExpressionUsage<?>> condition = Optional.empty();
	@Getter protected Optional<? extends ExpressionUsage<?>> until = Optional.empty();
	@Getter protected Optional<? extends ActionMapUsage<?, ?, ?>> body = Optional.empty();

	public WhileMapUsage(WhileLoopActionUsage sysmlElement, Mapper mapper) {
		super(sysmlElement,  mapper);
	}

	@Override
	public void fillSlots() {
		super.fillSlots();
		mapCondition();
		mapUntil();
		mapBody();
	}

	protected void mapCondition() {
		condition = Slots.mapAll(instance, this, Stream.ofNullable(sysmlElement.getWhileArgument()).toList(), Slots.<ExpressionUsage<?>>rawClassOf(ExpressionUsage.class)).stream().findFirst();

	}

	protected void mapBody() {
		body = Slots.mapAll(instance, this, Stream.ofNullable(sysmlElement.getBodyAction()).toList(), Slots.<ActionMapUsage<?, ?, ?>>rawClassOf(ActionMapUsage.class)).stream().findFirst();

	}

	protected void mapUntil() {
		until = Slots.mapAll(instance, this, Stream.ofNullable(sysmlElement.getUntilArgument()).toList(), Slots.<ExpressionUsage<?>>rawClassOf(ExpressionUsage.class)).stream().findFirst();

	}
}
