package Model.Predefined.MetaClasses.Action;

import Mapper.Mapper;
import Model.Definition;
import Model.EmptyCore;
import Model.Usage;
import lombok.Getter;
import org.omg.sysml.lang.sysml.Feature;
import org.omg.sysml.lang.sysml.SuccessionAsUsage;

import java.util.ArrayList;
import java.util.List;

// template: a library maps it by a subclass annotated with @MappedMetaClass(value = SuccessionAsUsage.class, core = EmptyCore.class)
public abstract class SuccessionMapUsage extends Usage<EmptyCore, SuccessionAsUsage, Definition<?,?>> {

	@Getter protected List<? extends ActionMapUsage<?, ?, ?>> targets = List.of();
	public SuccessionMapUsage(SuccessionAsUsage sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}


	@Override
	public void fillSlots() {
		super.fillSlots();
		mapTargets();
	}

	protected void mapTargets(){
		List<ActionMapUsage<?, ?, ?>> mapped = new ArrayList<>();
		mapped.add(instance.mapChain(List.of(sysmlElement.getSourceFeature()), this, ActionMapUsage.class));
		for (Feature target : sysmlElement.getTargetFeature()) {
			mapped.add(instance.mapChain(List.of(target), this, ActionMapUsage.class));
		}
		targets = mapped;
	}
}
