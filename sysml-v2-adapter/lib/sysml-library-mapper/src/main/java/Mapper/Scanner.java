package Mapper;

import Model.AbstractType;
import Model.Definition;
import Model.Usage;
import Model.Annotation.MappedLibrary;

import Model.Annotation.MappedMetaClass;
import Model.Core.Core;
import io.github.classgraph.AnnotationClassRef;
import io.github.classgraph.AnnotationParameterValueList;
import io.github.classgraph.ClassGraph;
import io.github.classgraph.ClassInfo;
import io.github.classgraph.ScanResult;
import lombok.Getter;
import lombok.extern.slf4j.Slf4j;
import org.omg.sysml.lang.sysml.Type;

import java.lang.reflect.Modifier;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.TypeVariable;
import java.util.*;

@Slf4j
public class Scanner {

	private final NewUtil newUtil;




	private static final List<?> anntations = List.of(MappedMetaClass.class.getName(), MappedLibrary.class.getName());

	@Getter
	private Map<String ,MappedLibraryTypeInfo> standardinfos = new HashMap<>();
	@Getter private Map<Class<? extends Type>,MetaclassInfo<?>> metaclassinfos = new HashMap<>();
	private final Map<Class<?>, Class<?>> definitionTypes = new HashMap<>();


	private MappedSort<MappedLibraryTypeInfo> mappedLibraryTypeInfos;
	private MappedSort<MetaclassInfo<?>> metaclassInfo;

	public Scanner(NewUtil newUtil) {
		this.newUtil = newUtil;
		scan();
	}


	private void scan() {
		try (ScanResult scanResult = new ClassGraph().enableAllInfo().scan()) {


			List<ClassInfo> infos = scanResult.getAllClasses().stream()
					.filter(info -> !info.isAbstract())
					.filter(this::hasAnnotation)
					.distinct()
					.toList();
			// all mappings in one result; on conflicts the subclass wins (see setClass)
			ScanMappedResult result = new ScanMappedResult();
			for (ClassInfo classInfo : infos) {
				handle(classInfo, result);
			}
			standardinfos = result.getStandardinfos();
			metaclassinfos = result.getMetaclassinfos();

			metaclassInfo = new MappedSort<MetaclassInfo<?>>(metaclassinfos.values());
			mappedLibraryTypeInfos = new MappedSort<MappedLibraryTypeInfo>(standardinfos.values());

			metaclassInfo.sort();
			mappedLibraryTypeInfos.sort();
			checkDefinitionTypes();


		}
	}

	private boolean hasAnnotation(ClassInfo classInfo) {
		int hit=0;
		for (Object annotation : anntations) {
			if(classInfo.hasAnnotation(annotation.toString())){
				hit++;
			}
		}
		if(hit==0){
			return false;
		}
		if(hit>1){
			throw new IllegalStateException("Class %s has more than one annotation: %s".formatted(classInfo.getName(), anntations));
		}

		if(!AbstractType.class.isAssignableFrom(classInfo.loadClass())){
			throw new IllegalStateException("Class %s is not a subclass of AbstractType".formatted(classInfo.getName()));
		}

		return  hit ==1;
	}






	public void handle(ClassInfo classInfo,ScanMappedResult c) {
		addMetaClass(classInfo,c);
	}

	private void addMetaClass(ClassInfo classInfo, ScanMappedResult scanMappedResult) {
		Class<? extends AbstractType<?, ?>> mappedClass = (Class<? extends AbstractType<?, ?>>) classInfo.loadClass();

		if(classInfo.hasAnnotation(MappedMetaClass.class)){
			AnnotationParameterValueList values = classInfo.getAnnotationInfo(MappedMetaClass.class).getParameterValues();
			Class<? extends Type> metaclass = getCastedClass(values.getValue("value"));
			MetaclassInfo<?> metaclassInfo = scanMappedResult.getMetaclassinfos().computeIfAbsent(metaclass, MetaclassInfo::new);
			Class<? extends Core<?>> core = getCoreClass(values.getValue("core"), mappedClass);
			checkConstructorFor(mappedClass, metaclass);
			metaclassInfo.setClass(mappedClass, core);
			log.debug("Found metaclass mapping: {} -> {} (core {})", classInfo.getName(), metaclassInfo.getMetaclass().getName(), core.getSimpleName());
		}

		if(classInfo.hasAnnotation(MappedLibrary.class)){
			AnnotationParameterValueList values = classInfo.getAnnotationInfo(MappedLibrary.class).getParameterValues();
			Class<? extends Core<?>> core = getCoreClass(values.getValue("core"), mappedClass);
			String libraryName = values.getValue("libraryName").toString();
			MappedLibraryTypeInfo mappedLibraryInfo = scanMappedResult.getStandardinfos()
					.computeIfAbsent(libraryName, name -> new MappedLibraryTypeInfo(newUtil, name));
			mappedLibraryInfo.setClass(mappedClass, core);
			log.debug("Found library mapping: {} -> {} (core {})", classInfo.getName(), libraryName, core.getSimpleName());
		}
	}

	// the metaclass is known from the annotation, so the (element, Mapper) constructor must accept it
	private void checkConstructorFor(Class<?> mappedClass, Class<? extends Type> metaclass) {
		boolean found = Arrays.stream(mappedClass.getConstructors())
				.anyMatch(c -> c.getParameterCount() == 2 && c.getParameterTypes()[0].isAssignableFrom(metaclass) && c.getParameterTypes()[1].isAssignableFrom(Mapper.class));
		if (!found) {
			throw new IllegalStateException("Class %s is mapped to %s but has no public constructor (%s, Mapper)"
					.formatted(mappedClass.getName(), metaclass.getSimpleName(), metaclass.getSimpleName()));
		}
	}

	// loads the core named in the annotation and checks that it fits the core type parameter of the mapped class
	private Class<? extends Core<?>> getCoreClass(Object value, Class<?> mappedClass) {
		if (!(value instanceof AnnotationClassRef ref) || !Core.class.isAssignableFrom(ref.loadClass())) {
			throw new IllegalStateException("Class %s: 'core' must name a subclass of Core".formatted(mappedClass.getName()));
		}
		Class<? extends Core<?>> core = (Class<? extends Core<?>>) ref.loadClass();
		if (Modifier.isAbstract(core.getModifiers())) {
			throw new IllegalStateException("Class %s: core %s is abstract".formatted(mappedClass.getName(), core.getName()));
		}
		for (Class<?> required : requiredCoreTypes(mappedClass)) {
			if (!required.isAssignableFrom(core)) {
				throw new IllegalStateException("Class %s: core %s does not fit the core type %s"
						.formatted(mappedClass.getName(), core.getSimpleName(), required.getSimpleName()));
			}
		}
		return core;
	}

	// resolves the core type parameter of AbstractType for the given class; type variables yield their bounds
	private List<Class<?>> requiredCoreTypes(Class<?> mappedClass) {
		return resolveTypeArgument(mappedClass, AbstractType.class, 1);
	}

	// definition type a usage class accepts, read from the D parameter of Usage
	public Class<?> requiredDefinitionType(Class<?> usageClass) {
		return definitionTypes.computeIfAbsent(usageClass, c -> {
			List<Class<?>> types = resolveTypeArgument(c, Usage.class, 2);
			if (types.size() > 1) {
				throw new IllegalStateException("Class %s: the definition type D must have a single bound, found %s".formatted(c.getName(), types));
			}
			return types.isEmpty() ? Definition.class : types.getFirst();
		});
	}

	// resolves type parameter `index` of `base` as seen from `clazz`
	private List<Class<?>> resolveTypeArgument(Class<?> clazz, Class<?> base, int index) {
		Map<TypeVariable<?>, java.lang.reflect.Type> bindings = new HashMap<>();
		Class<?> current = clazz;
		while (current != null && current != base) {
			java.lang.reflect.Type superType = current.getGenericSuperclass();
			if (superType instanceof ParameterizedType parameterized && parameterized.getRawType() instanceof Class<?> raw) {
				TypeVariable<?>[] variables = raw.getTypeParameters();
				java.lang.reflect.Type[] arguments = parameterized.getActualTypeArguments();
				for (int i = 0; i < variables.length; i++) {
					bindings.put(variables[i], bindings.getOrDefault(arguments[i], arguments[i]));
				}
				current = raw;
			} else {
				current = current.getSuperclass();
			}
		}
		return erasures(bindings.get(base.getTypeParameters()[index]));
	}

	// a metaclass usage has no fixed library type, so its D must at least be met by one mapped definition class
	private void checkMetaclassDefinitionTypes() {
		List<Class<?>> definitionClasses = new ArrayList<>();
		standardinfos.values().forEach(info -> info.getDefinitionClass().ifPresent(definitionClasses::add));
		metaclassinfos.values().stream().map(MetaclassInfo::getMappedClass)
				.filter(Definition.class::isAssignableFrom).forEach(definitionClasses::add);

		for (MetaclassInfo<?> info : metaclassinfos.values()) {
			if (!Usage.class.isAssignableFrom(info.getMappedClass())) continue;
			Class<?> required = requiredDefinitionType(info.getMappedClass());
			if (required == Definition.class) continue;
			if (definitionClasses.stream().noneMatch(required::isAssignableFrom)) {
				throw new IllegalStateException("%s expects definition %s, but no mapped definition class is a %s"
						.formatted(info.getMappedClass().getSimpleName(), required.getSimpleName(), required.getSimpleName()));
			}
		}
	}

	// every usage class must accept the definition class built for its library type
	private void checkDefinitionTypes() {
		checkMetaclassDefinitionTypes();
		for (MappedLibraryTypeInfo info : standardinfos.values()) {
			if (info.getUsageClass().isEmpty()) continue;
			Optional<MappedLibraryTypeInfo> definitionInfo = mappedLibraryTypeInfos.get(info.getElement());
			if (definitionInfo.isEmpty() || definitionInfo.get().getDefinitionClass().isEmpty()) continue;
			Class<?> definitionClass = definitionInfo.get().getDefinitionClass().get();
			Class<?> required = requiredDefinitionType(info.getUsageClass().get());
			if (!required.isAssignableFrom(definitionClass)) {
				throw new IllegalStateException("%s expects definition %s, but library type %s builds %s"
						.formatted(info.getUsageClass().get().getSimpleName(), required.getSimpleName(), info.getLibraryName(), definitionClass.getSimpleName()));
			}
		}
	}

	private List<Class<?>> erasures(java.lang.reflect.Type type) {
		if (type instanceof Class<?> c) return List.of(c);
		if (type instanceof ParameterizedType p && p.getRawType() instanceof Class<?> raw) return List.of(raw);
		if (type instanceof TypeVariable<?> variable) {
			List<Class<?>> result = new ArrayList<>();
			for (java.lang.reflect.Type bound : variable.getBounds()) result.addAll(erasures(bound));
			return result;
		}
		return List.of();
	}

	private boolean isOfClass(Object type){
		return type instanceof AnnotationClassRef clazz && Type.class.isAssignableFrom(clazz.loadClass());
	}

	private Class<? extends Type> getCastedClass(Object type) {
		if(!isOfClass(type)){
			throw new IllegalStateException("Class %s is not a subclass of Element".formatted(type.getClass().getName()));
		}
		return ((AnnotationClassRef) type).loadClass().asSubclass(Type.class);
	}


	public <T extends AbstractType<?,?>,C extends Type> Optional<T> getMappedClass(C element,Mapper mapper,Class<T>clazz) {
		// library types are preferred; metaclass mappings are the fallback
		Optional<MappedLibraryTypeInfo> library = mappedLibraryTypeInfos.get(element);
		if (library.isPresent()) {
			logLibraryFallback(element, library.get());
			return Optional.of(clazz.cast(library.get().create(element, mapper)));
		}
		Optional<MetaclassInfo<?>> metaclass = metaclassInfo.get(element);
		metaclass.ifPresent(info -> logMetaclassSupertype(element, info));
		return metaclass.map(info -> clazz.cast(info.create(element, mapper)));
	}

	// each fallback combination is logged once per run, not once per element
	private final Set<String> loggedFallbacks = new HashSet<>();

	// a more specific library type had no class for this kind of element, so a parent library type is used
	private void logLibraryFallback(Type element, MappedLibraryTypeInfo used) {
		for (MappedLibraryTypeInfo skipped : standardinfos.values()) {
			if (skipped == used || !skipped.isSpecilizedBy(element) || !skipped.specialices(used)) continue;
			String kind = element.eClass().getName();
			if (loggedFallbacks.add(skipped.getLibraryName() + "|" + kind + "|" + used.getLibraryName())) {
				log.info("'{}' ({}): {} has no class for it, using {}", element.path(), kind, skipped.getLibraryName(), used.getLibraryName());
			}
		}
	}

	// no class is mapped for the exact metaclass of the element, so a mapped supertype catches it
	private void logMetaclassSupertype(Type element, MetaclassInfo<?> used) {
		Class<?> exact = element.eClass().getInstanceClass();
		if (exact == used.getMetaclass()) return;
		if (loggedFallbacks.add(exact.getName() + "|" + used.getMetaclass().getName())) {
			log.warn("'{}' is a {}, no class is mapped for it, using supertype {} -> {}", element.path(), exact.getSimpleName(), used.getMetaclass().getSimpleName(), used.getMappedClass().getSimpleName());
		}
	}

	public Optional<AbstractType<?, ?>> getMappedClass(Type element,Mapper mapper) {

		return getMappedClass(element,mapper,(Class<AbstractType<?, ?>>) (Class<?>) AbstractType.class);
	}


}
