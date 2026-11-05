package Model.Predefined.MetaClasses.Action;

import Mapper.Mapper;
import Model.Predefined.MetaClasses.Expression.ExpressionUsage;
import Model.Slots;
import Model.Usage;
import lombok.Getter;
import org.omg.sysml.lang.sysml.ForLoopActionUsage;

import java.util.Optional;
import java.util.stream.Stream;

// template: a library maps it by a subclass annotated with @MappedMetaClass(value = ForLoopActionUsage.class, core = EmptyActionCore.class)
public abstract class ForLoopMapUsage extends ActionMapUsage<EmptyActionCore, ForLoopActionUsage, ActionMapDefinition<EmptyActionCore>> {

	@Getter protected Optional<? extends Usage<?, ?,?>> loopVariable = Optional.empty();
	@Getter protected Optional<? extends ExpressionUsage<?>> collection = Optional.empty();
	@Getter protected Optional<? extends ActionMapUsage<?, ?, ?>> body = Optional.empty();

	public ForLoopMapUsage(ForLoopActionUsage sysmlElement, Mapper newMappe) {
		super(sysmlElement, newMappe);
	}

	@Override
	public void fillSlots() {
		super.fillSlots();
		mapLoopVariable();
		mapCollection();
		mapBody();
	}

	protected void mapLoopVariable() {
		loopVariable = Slots.mapAll(instance, this, Stream.ofNullable(sysmlElement.getLoopVariable()).toList(), Slots.<Usage<?, ?,?>>rawClassOf(Usage.class)).stream().findFirst();
	}

	protected void mapCollection() {
		collection = Slots.mapAll(instance, this, Stream.ofNullable(sysmlElement.getSeqArgument()).toList(), Slots.<ExpressionUsage<?>>rawClassOf(ExpressionUsage.class)).stream().findFirst();
	}

	protected void mapBody() {
		body = Slots.mapAll(instance, this, Stream.ofNullable(sysmlElement.getBodyAction()).toList(), Slots.<ActionMapUsage<?, ?, ?>>rawClassOf(ActionMapUsage.class)).stream().findFirst();
	}
}
