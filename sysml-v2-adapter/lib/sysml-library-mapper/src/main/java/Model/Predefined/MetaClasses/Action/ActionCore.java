package Model.Predefined.MetaClasses.Action;

import Mapper.Mapper;
import Model.AbstractType;
import Model.Core.Core;
import Model.Slots;
import Model.Usage;
import lombok.Getter;
import org.omg.sysml.lang.sysml.*;

import java.util.ArrayList;
import java.util.List;

public class ActionCore extends Core<Type> {

	@Getter protected List<? extends Usage<?, ?,?>> inputs = new ArrayList<>();
	@Getter protected List<? extends Usage<?, ?,?>> outputs = new ArrayList<>();
	@Getter protected List<? extends ActionMapUsage<?, ?, ?>> actions = List.of();
	@Getter protected List<? extends SuccessionMapUsage> successions = List.of();

	public ActionCore(Type sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	@Override
	public void fillSlots(AbstractType<?, ?> owner) {
		mapInputs(owner);
		mapOutputs(owner);
		mapActions(owner);
		mapSuccessions(owner);
	}

	protected void mapInputs(AbstractType<?, ?> owner) {
		List<Feature> in = sysmlElement.getInput();
		inputs = Slots.mapAll(mapper, owner, in, Slots.rawClassOf(Usage.class));
	}

	protected void mapOutputs(AbstractType<?, ?> owner) {
		List<Feature> out = sysmlElement.getOutput();
		outputs = Slots.mapAll(mapper, owner, out, Slots.rawClassOf(Usage.class));
	}

	protected void mapActions(AbstractType<?, ?> owner) {
		actions = mapper.mapOwnedElement(ActionUsage.class, owner, Slots.<ActionMapUsage<?, ?, ?>>rawClassOf(ActionMapUsage.class));
	}

	protected void mapSuccessions(AbstractType<?, ?> owner) {
		successions = mapper.mapOwnedElement(SuccessionAsUsage.class, owner, SuccessionMapUsage.class);
	}
}
