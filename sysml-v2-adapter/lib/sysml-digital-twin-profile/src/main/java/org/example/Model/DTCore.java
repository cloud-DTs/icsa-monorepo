package org.example.Model;

import Mapper.Mapper;
import Model.AbstractType;
import Model.Core.Core;
import org.omg.sysml.lang.sysml.Element;
import org.omg.sysml.lang.sysml.Feature;
import org.omg.sysml.lang.sysml.MetadataUsage;
import org.omg.sysml.lang.sysml.Type;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

// base core of the DigitalTwinLibrary: every feature written in the model has to land in a slot, nothing is skipped silently
public abstract class DTCore extends Core<Type> {

	private final Set<Element> inSlots = new HashSet<>();

	protected DTCore(Type sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	@Override
	public final void fillSlots(AbstractType<?, ?> owner) {
		inSlots.clear();
		List<Feature> features = ownFeatures(owner);
		fillDTSlots(owner, features);
		for (Feature feature : features) {
			if (!inSlots.contains(feature)) {
				throw new IllegalArgumentException("'%s': '%s' does not fit any slot of %s"
						.formatted(owner.getName(), feature.getName(), owner.getClass().getSimpleName()));
			}
		}
	}

	protected abstract void fillDTSlots(AbstractType<?, ?> owner,List<Feature> features);

	protected <T extends AbstractType<?, ?>> List<T> slot(List<T> mapped) {
		mapped.forEach(element -> inSlots.add(element.getSysmlElement()));
		return mapped;
	}

	protected List<Feature> ownFeatures(AbstractType<?, ?> owner) {
		return owner.getSysmlElement().getFeature().stream()
				.filter(feature -> !mapper.getNewUtil().isfromLibraryRawType(feature) && !mapper.getNewUtil().isFromStandardLibrary(feature)
						&& !MetadataUsage.class.isInstance(feature)).toList();
	}
}
