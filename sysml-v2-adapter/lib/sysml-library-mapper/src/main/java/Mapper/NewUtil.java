package Mapper;

import Model.ElemWithMult;
import lombok.Getter;
import org.eclipse.emf.common.util.EList;
import org.eclipse.emf.ecore.EObject;
import org.eclipse.emf.ecore.resource.Resource;

import org.omg.sysml.interactive.SysMLInteractive;
import org.omg.sysml.lang.sysml.*;
import org.omg.sysml.util.ElementUtil;
import org.omg.sysml.util.FeatureUtil;

import java.lang.Class;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.HashSet;
import java.util.Set;
import java.util.stream.Collectors;



public class NewUtil {

	@Getter  private final ResourceContainer resourceContainer;


	private static final Set<String> TECHNICAL_KIND_OWNERS = Set.of("TwinLibraryElement", "TwinLibraryElementConnection", "TwinLibraryElementCalcDef", "TwinLibraryElementActionDef", "TwinLibraryElementAttributeDef", "TwinLibraryElementPortDef", "TwinLibraryElementStateDef");


	public NewUtil(ResourceContainer resourceContainer) {
		this.resourceContainer = resourceContainer;
	}

	public static Element getRootElementFromResource(Resource resource) {
		EList<EObject> contents = resource.getContents();
		return contents.isEmpty() ? null : (Element)contents.get(0);
	}



	public Type getLibrayType(String libraryName) {
		return resourceContainer.getLibraryResources().getLibraryType(libraryName);
	}

	public boolean isfromLibraryRawType(Element element) {
		return resourceContainer.isPartOfLibraryResources(element);
	}

	public boolean redefinesOrSubsets(Feature candidate, String targetName) {
		if (targetName == null) return true;
		Set<Feature> visited = new HashSet<>();
		Deque<Feature> toCheck = new ArrayDeque<>();
		toCheck.add(candidate);
		while (!toCheck.isEmpty()) {
			Feature current = toCheck.poll();
			if (!visited.add(current)) continue;
			if (targetName.equals(current.getName())) return true;
			for (Redefinition r : current.getOwnedRedefinition()) toCheck.add(r.getRedefinedFeature());
			for (Subsetting s : current.getOwnedSubsetting()) toCheck.add((Feature) s.getGeneral());
		}
		return false;
	}
	public <T extends Element> Set<T> collect(Class<T> clazz) {
		return resourceContainer.getUserResources().getAllElements().stream().filter(clazz::isInstance).map(clazz::cast).collect(Collectors.toSet());
	}
	public Type convertBasicFeatureToType(Type feature) {
		if (feature instanceof Feature featureType) {
			return (Type) FeatureUtil.getBasicFeatureOf(featureType);
		}
		return feature;
	}
	public boolean isTechnicalKindFeature(Feature feature) {
		if (!"kind".equals(feature.getName())) {
			return false;
		}

		Type owner = feature.getOwningType();

		return owner != null && TECHNICAL_KIND_OWNERS.contains(owner.getName());
	}

	public boolean isFromStandardLibrary(Element element) {
		return ElementUtil.isStandardLibraryElement(element);
	}



	public static ElemWithMult getMultiplicityRange(Type type) {
		MultiplicityRange mult = FeatureUtil.getMultiplicityRangeOf(type.getMultiplicity());
		if (mult != null) {
			int lower = mult.valueOf(mult.getLowerBound());
			int upper = mult.valueOf(mult.getUpperBound());
			if (lower < 0) lower = upper;

			return new ElemWithMult(lower, upper);
		} else {
			return new ElemWithMult(1, 1);
		}
	}


}
