package Mapper;

import Model.AbstractType;
import Model.Core.Core;
import Model.Definition;
import Model.Usage;
import lombok.Getter;
import org.omg.sysml.lang.sysml.Classifier;
import org.omg.sysml.lang.sysml.Feature;
import org.omg.sysml.lang.sysml.Type;
import org.omg.sysml.util.TypeUtil;

import java.util.Optional;

public class MappedLibraryTypeInfo implements MappedComprable<Type, MappedLibraryTypeInfo> {
	@Getter private final String libraryName;
	@Getter private final Type element;
	@Getter private Optional<Class<? extends AbstractType<?, ?>>> definitionClass = Optional.empty();
	@Getter private Optional<Class<? extends AbstractType<?, ?>>> usageClass = Optional.empty();
	@Getter private Class<? extends Core<?>> definitionCore;
	@Getter private Class<? extends Core<?>> usageCore;

	public MappedLibraryTypeInfo(NewUtil newUtil, String libraryName) {
		this.element = newUtil.getLibrayType(libraryName);
		this.libraryName = libraryName;
		if (element == null) {
			throw new IllegalStateException("Library type '%s' not found in the loaded libraries".formatted(libraryName));
		}
	}

	// a subclass of the mapped class replaces it; unrelated classes for the same library type are ambiguous
	public void setClass(Class<? extends AbstractType<?, ?>> mappedClass, Class<? extends Core<?>> core) {
		if (Definition.class.isAssignableFrom(mappedClass)) {
			if (replaces(definitionClass, mappedClass, "definition")) {
				definitionClass = Optional.of(mappedClass);
				definitionCore = core;
			}
			return;
		}
		if (Usage.class.isAssignableFrom(mappedClass)) {
			if (replaces(usageClass, mappedClass, "usage")) {
				usageClass = Optional.of(mappedClass);
				usageCore = core;
			}
			return;
		}
		throw new IllegalStateException("Class %s is not a subclass of Definition or Usage".formatted(mappedClass.getName()));
	}

	private boolean replaces(Optional<Class<? extends AbstractType<?, ?>>> current, Class<?> candidate, String kind) {
		if (current.isEmpty() || current.get().isAssignableFrom(candidate)) return true;
		if (candidate.isAssignableFrom(current.get())) return false;
		throw new IllegalStateException("Library type %s has unrelated %s classes %s and %s".formatted(libraryName, kind, current.get().getName(), candidate.getName()));
	}

	@Override
	public boolean specialices(MappedLibraryTypeInfo other) {
		return TypeUtil.specializes(element, other.element);
	}

	@Override
	public boolean isSpecilizedBy(Type element) {
		return TypeUtil.specializes(element, this.element);
	}

	@Override
	public boolean canCreate(Type element) {
		if (element instanceof Classifier) return definitionClass.filter(c -> accepts(c, element)).isPresent();
		if (element instanceof Feature) return usageClass.filter(c -> accepts(c, element)).isPresent();
		return false;
	}

	@Override
	public AbstractType<?, ?> create(Type element, Mapper mapper) {
		if (element instanceof Classifier) return instantiate(definitionClass.orElseThrow(), definitionCore, element, mapper);
		return instantiate(usageClass.orElseThrow(), usageCore, element, mapper);
	}
}
