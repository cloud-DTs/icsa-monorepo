package Model;

import Mapper.Mapper;
import Model.Core.Core;
import lombok.Getter;

import org.omg.sysml.lang.sysml.*;
import org.omg.sysml.util.TypeUtil;

import java.lang.Class;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.function.Supplier;
import Mapper.NewUtil;

public abstract class Usage<C extends Core<? super U>, U extends Feature,D extends Definition<?,?>> extends AbstractType<U, C> {



	@Getter private ElemWithMult multiplicity;
	@Getter private List<Usage<?, ?, ?>> specializations = List.of();
	@Getter private Optional<D> definition = Optional.empty();

	protected Usage(U sysmlElement, Mapper newMappe) {
		super(sysmlElement,newMappe);
		multiplicity = NewUtil.getMultiplicityRange(sysmlElement);
	}

	@Override
	public void fillSlots() {
		super.fillSlots();
		specializations = mapSpecializations();
		List<Classifier> definitions = sysmlElement.getType().stream()
				.filter(Classifier.class::isInstance).map(Classifier.class::cast)
				.filter(x -> !instance.getNewUtil().isFromStandardLibrary(x)).toList();
		if (definitions.isEmpty()){
			return;
		}
		Classifier def = mostSpecificDefinition(definitions);
		AbstractType<?, ?> mappedDef = instance.map(def, null);
		if(mappedDef == null){
			return;
		}
		// typed map throws a clear error if the definition does not fit the D of this usage class
		definition = Optional.of(instance.map(def, null, Slots.<D>rawClassOf(instance.getRequiredDefinitionType(getClass()))));
	}

	private Classifier mostSpecificDefinition(List<Classifier> definitions){
		List<Classifier> mostSpecific = definitions.stream().filter(candidate -> definitions.stream().filter(other -> other != candidate).noneMatch(other -> TypeUtil.getSupertypesOf(other, true).contains(candidate))).toList();

		if (mostSpecific.size() == 1) {
			return mostSpecific.getFirst();
		}

		if (mostSpecific.isEmpty()) {
			throw new IllegalArgumentException("No most specific definition found.");
		}

		throw new IllegalArgumentException("Multiple unrelated definitions found: " + mostSpecific.stream().map(Classifier::getQualifiedName).toList());
	}

	private List<Usage<?, ?, ?>> mapSpecializations() {
		Class<Usage<?, ?, ?>> usageClass = Slots.rawClassOf(Usage.class);
		List<Usage<?, ?, ?>> result = new ArrayList<>();
		for (Subsetting subsetting : sysmlElement.getOwnedSubsetting()) {
			if (subsetting instanceof ReferenceSubsetting) {
				continue;
			}
			Feature general = subsetting.getSubsettedFeature();
			if (general == null || instance.getNewUtil().isfromLibraryRawType(general) || instance.getNewUtil().isFromStandardLibrary(general)) {
				continue;
			}
			result.add(instance.mapChain(general.getChainingFeature().isEmpty() ? List.of(general) : general.getChainingFeature(), this, usageClass));
		}
		return result;
	}

	public Optional<FeatureDirectionKind> getDirection() {
		FeatureDirectionKind direction = sysmlElement.getDirection();
		if (direction == null) return Optional.empty();
		return Optional.of(direction);
	}




}
