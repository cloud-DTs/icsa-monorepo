package Mapper;



import Model.AbstractType;
import Model.ElemWithMult;
import lombok.Getter;
import lombok.extern.slf4j.Slf4j;
import org.omg.sysml.lang.sysml.Element;
import org.omg.sysml.lang.sysml.Feature;
import org.omg.sysml.lang.sysml.Package;
import org.omg.sysml.lang.sysml.Type;
import org.omg.sysml.util.FeatureUtil;


import java.nio.charset.StandardCharsets;
import java.util.*;

@Slf4j
public class Mapper {


	Scanner scanner;
	@Getter
	NewUtil newUtil;

	@Getter private Map<UUID, AbstractType<?,?>> mapperMap = new HashMap<>();


	public Mapper(Scanner scanner,NewUtil newUtil) {
		this.scanner = scanner;
		this.newUtil = newUtil;
	}

	// definition type the given usage class accepts (from its D type parameter)
	public Class<?> getRequiredDefinitionType(Class<?> usageClass) {
		return scanner.requiredDefinitionType(usageClass);
	}

	public void parse() {
		for(RawType rawType:List.of(newUtil.getResourceContainer().getLibraryResources(), newUtil.getResourceContainer().getUserResources())){
			for (Element rootElement : rawType.getRootElement()) {
				start(rootElement);
			}
		}

	}

	public void start(org.omg.sysml.lang.sysml.Element element) {
		for (org.omg.sysml.lang.sysml.Element el : element.getOwnedElement()) {
			if (el instanceof Package) {
				start(el);
			}
			if (el instanceof Type elType) {
				map(elType, null);
			}
		}
	}

	protected UUID idCalculation(Type sysmlElement, AbstractType<?,?> owner) {
		String path = sysmlElement.path();
		if (owner != null) {
			path = owner.getId() + "|" + path;
		}
		return UUID.nameUUIDFromBytes(path.getBytes(StandardCharsets.UTF_8));

	}

	public <T extends AbstractType<?,?>> T map(Type sysmlElement, AbstractType<?,?> owner, Class<T> type) {
		AbstractType<?,?> mapped = map(sysmlElement, owner);
		if (!type.isInstance(mapped)) {
			throw new IllegalStateException("Element '%s' mapped as %s, expected %s".formatted(sysmlElement.getName(), mapped == null ? "nothing" : mapped.getClass().getSimpleName(), type.getSimpleName()));
		}
		return type.cast(mapped);
	}

	public AbstractType<?,?> map(Type sysmlElement, AbstractType<?,?> owner) {
		for (AbstractType<?,?> p = owner; p != null; p = p.getParent().orElse(null)) {
			if (p.getSysmlElement() == sysmlElement) {
				throw new IllegalStateException("Recursive structure: '%s' contains itself (in '%s')"
						.formatted(sysmlElement.getName(), owner.getName()));
			}
		}
		UUID id = idCalculation(sysmlElement, owner);
		AbstractType<?,?> existing = mapperMap.get(id);
		if (existing != null) return existing;


		Optional<AbstractType<?,?>> otionalCreated = scanner.getMappedClass(sysmlElement,this);
		if (otionalCreated.isEmpty()) return null;

		AbstractType<?,?> created = otionalCreated.get();

		created.setId(id);
		created.setParent(owner);
		created.setInherited(owner != null && (owner.isInherited() || !isOwnedBy(sysmlElement, owner.getSysmlElement())));		created.setLibrary(newUtil.isfromLibraryRawType(sysmlElement));
		mapperMap.put(id, created);
		log.info("Mapped element '%s' as %s (id=%s,path=%s)".formatted(sysmlElement.getName(), created.getClass().getSimpleName(), id, sysmlElement.path()));
		if (!created.isLibrary()) {
			created.fillSlots();
		}
		return created;
	}
	protected boolean isOwnedBy(Element element, Element owner) {
		for (Element current = element.getOwner(); current != null; current = current.getOwner()) {
			if (current == owner) {
				return true;
			}
		}
		return false;
	}

	public <T extends AbstractType<?,?>> List<T> mapSlot(String slotName, AbstractType<?,?> owner, Class<T> type) {
		List<T> result = new ArrayList<>();
		for (Feature feature : owner.getSysmlElement().getFeature()) {

			if (newUtil.isfromLibraryRawType(feature)){
				if(!owner.isLibrary()){
					continue;
				}
			}
			if (!newUtil.redefinesOrSubsets(feature, slotName)){
				continue;
			}

			AbstractType<?,?> mapped = map(feature, owner);
			if (!type.isInstance(mapped)) {
				throw new IllegalStateException("Slot '%s': '%s' mapped as %s, expected %s".formatted(slotName, feature.getName(), mapped == null ? "nothing" : mapped.getClass().getSimpleName(), type.getSimpleName()));
			}
			result.add(type.cast(mapped));
		}
		return result;

	}

	public <T extends AbstractType<?,?>> T mapSingleSlot(String slotName, AbstractType<?,?> owner, Class<T> type) {
		List<T> result = mapSlot(slotName, owner, type);
		if (result.size() > 1) {
			throw new IllegalStateException("Slot '%s' has multiple mappings: %s".formatted(slotName, result));
		}
		return result.isEmpty() ? null : result.get(0);
	}

	public <T extends AbstractType<?,?>,S extends Type> List<T> mapOwnedElement(Class<S> sysmlMetaclass, AbstractType<?,?> owner, Class<T> type) {
		List<T> result = new ArrayList<>();

		for (org.omg.sysml.lang.sysml.Element member : owner.getSysmlElement().getOwnedMember()) {
			if (!sysmlMetaclass.isInstance(member)) {
				continue;
			}
			S typedMember = sysmlMetaclass.cast(member);

			AbstractType<?,?> mapped = map(typedMember, owner);

			if (type.isInstance(mapped)) {
				result.add(type.cast(mapped));
			}
			else {
				throw new IllegalArgumentException("Owned element '%s' mapped as %s, expected %s".formatted(typedMember.getName(), mapped == null ? "nothing" : mapped.getClass().getSimpleName(), type.getSimpleName()));
			}
		}

		return  result;
	}


	public <T extends AbstractType<?,?>> T mapChain(List<Feature> chain, AbstractType<?,?> context, Class<T> type) {
		Feature first = chain.getFirst();
		AbstractType<?,?> scope = context;
		Optional<Feature> start = Optional.empty();
		while (scope != null && (start = featureIn(scope, first)).isEmpty()){
			scope = scope.getParent().orElse(null);
		}
		AbstractType<?,?> current = map(start.orElse(first), scope);
		for (Feature link : chain.subList(1, chain.size())) {
			if (current == null) break;
			current = map(featureIn(current, link).orElse(link), current);
		}
		if (!type.isInstance(current)) throw new IllegalStateException("Chain %s mapped as %s, expected %s"
				.formatted(chain.stream().map(Feature::getName).toList(), current == null ? "nothing" : current.getClass().getSimpleName(), type.getSimpleName()));
		return type.cast(current);
	}

	private Optional<Feature> featureIn(AbstractType<?,?> owner, Feature target) {
		return owner.getSysmlElement().getFeature().stream()
				.filter(feature -> feature == target || FeatureUtil.getAllRedefinedFeaturesOf(feature).contains(target))
				.findFirst();
	}



}

