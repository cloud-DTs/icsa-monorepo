package Rules;


import Executor.GenerelRules;
import Mapper.NewUtil;
import Model.ElemWithMult;
import org.omg.sysml.lang.sysml.*;
import org.omg.sysml.util.TypeUtil;

import java.util.HashSet;
import java.util.Set;
import java.util.stream.Collectors;

public class MultiplicityRule extends GenerelRules {

	public MultiplicityRule(NewUtil utils) {
		super(utils);
	}

	@Override
	public boolean isValid() throws IllegalArgumentException {
		Set<Type> userTypes = utilsManager.collect(Type.class);

		for (Type userType : userTypes) {
			if (!(userType instanceof Usage || userType instanceof Definition)) {
				continue;
			}
			validateType(userType, new HashSet<>());
		}
		return true;
	}

	private void validateType(Type userType, Set<Type> visited) throws IllegalArgumentException {

		if (!visited.add(userType)) {
			return;
		}

		if (utilsManager.isFromStandardLibrary(userType) || utilsManager.isfromLibraryRawType(userType)) {
			return;
		}

		Set<Feature> features = new HashSet<>(TypeUtil.getPublicFeaturesOf(userType));

		features.addAll(userType.getOwnedFeature());

		for (Feature feature : features) {
			if (utilsManager.isTechnicalKindFeature(feature)) {
				continue;
			}

			if (utilsManager.isFromStandardLibrary(feature)) {
				continue;
			}

			validateInheritedFeature(userType, feature);

			if (feature instanceof Usage usage) {
				validateType(usage, visited);
			}
		}
	}

	private void validateInheritedFeature(Type userType, Feature inheritedFeature) throws IllegalArgumentException {

		Set<Feature> specializingFeatures = userType.getFeature().stream().filter(feature -> directlySpecializes(feature, inheritedFeature)).collect(Collectors.toSet());
		ElemWithMult parentMultiplicity = NewUtil.getMultiplicityRange(inheritedFeature);

		if (utilsManager.isfromLibraryRawType(inheritedFeature)) {
			validateLowerBound(userType, inheritedFeature, parentMultiplicity, specializingFeatures);
		}
		validateUpperBound(userType, inheritedFeature, parentMultiplicity, specializingFeatures);
	}

	private boolean directlySpecializes(Feature child, Feature parent) {
		boolean redefines = child.getOwnedRedefinition().stream().map(Redefinition::getRedefinedFeature).anyMatch(parent::equals);
		boolean subsets = child.getOwnedSubsetting().stream().map(Subsetting::getGeneral).map(utilsManager::convertBasicFeatureToType).anyMatch(parent::equals);
		return redefines || subsets;
	}

	private void validateLowerBound(Type context, Feature parent, ElemWithMult parentMultiplicity, Set<Feature> children) throws IllegalArgumentException {
		int lowerSum = children.stream().map(NewUtil::getMultiplicityRange).mapToInt(ElemWithMult::getLowerBound).sum();
		if (lowerSum < parentMultiplicity.getLowerBound()) {
			throw new IllegalArgumentException(("Type '%s' does not fully concretize required feature '%s': " + "combined lower multiplicity is %d, required is %d.").formatted(getTypeName(context), getFeatureName(parent), lowerSum, parentMultiplicity.getLowerBound()));
		}
	}

	private void validateUpperBound(Type context, Feature parent, ElemWithMult parentMultiplicity, Set<Feature> children) throws IllegalArgumentException {
		int parentUpper = parentMultiplicity.getUpperBound();
		if (parentUpper == -1) {
			return;
		}
		for (Feature child : children) {
			ElemWithMult childMultiplicity = NewUtil.getMultiplicityRange(child);
			if (childMultiplicity.getUpperBound() == -1) {
				throw new IllegalArgumentException(("Feature '%s' in type '%s' has multiplicity %s, " + "but parent feature '%s' has bounded multiplicity %s.").formatted(getFeatureName(child), getTypeName(context), formatMultiplicity(childMultiplicity), getFeatureName(parent), formatMultiplicity(parentMultiplicity)));
			}
		}
		int upperSum = children.stream().map(NewUtil::getMultiplicityRange).mapToInt(ElemWithMult::getUpperBound).sum();
		if (upperSum > parentUpper) {
			throw new IllegalArgumentException(("Features [%s] in type '%s' exceed the upper multiplicity " + "of feature '%s': %d > %d.").formatted(formatFeatureNames(children), getTypeName(context), getFeatureName(parent), upperSum, parentUpper));
		}
	}

	private String formatFeatureNames(Set<Feature> features) {
		return features.stream().map(this::getFeatureName).sorted().collect(Collectors.joining(", "));
	}

	private String formatMultiplicity(ElemWithMult multiplicity) {
		String upper = multiplicity.getUpperBound() == -1 ? "*" : String.valueOf(multiplicity.getUpperBound());

		return "[%d..%s]".formatted(multiplicity.getLowerBound(), upper);
	}

	private String getTypeName(Type type) {
		if (type.getQualifiedName() != null) {
			return type.getQualifiedName();
		}

		if (type.getName() != null) {
			return type.getName();
		}

		return "<unnamed type>";
	}

	private String getFeatureName(Feature feature) {
		if (feature.getQualifiedName() != null) {
			return feature.getQualifiedName();
		}

		if (feature.getName() != null) {
			return feature.getName();
		}

		return "<unnamed feature>";
	}
}