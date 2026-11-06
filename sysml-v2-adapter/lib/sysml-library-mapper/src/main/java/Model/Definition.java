package Model;

import Mapper.Mapper;
import Model.Core.Core;
import lombok.Getter;

import org.omg.sysml.lang.sysml.Classifier;
import org.omg.sysml.lang.sysml.Subclassification;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

public abstract class Definition<C extends Core<? super D>, D extends Classifier> extends AbstractType<D, C>
{
	@Getter private List<Definition<?, ?>> superDefinitions = List.of();

	public Definition(D sysmlElement, Mapper newMappe) {
		super(sysmlElement, newMappe);
	}

	@Override
	public void fillSlots() {
		super.fillSlots();
		List<Classifier> generals = new ArrayList<>();
		for (Subclassification subclassification : sysmlElement.getOwnedSubclassification()) {
			Classifier general = subclassification.getSuperclassifier();
			if (general == null || instance.getNewUtil().isFromStandardLibrary(general)) {
				continue;
			}
			generals.add(general);
		}
		superDefinitions = Slots.mapAll(instance, null, generals, Slots.<Definition<?, ?>>rawClassOf(Definition.class));
	}
}
