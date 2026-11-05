package Mapper;

import Model.AbstractType;
import Model.Core.Core;
import lombok.Getter;
import org.omg.sysml.lang.sysml.Type;

public class MetaclassInfo<T extends Type> implements MappedComprable<T, MetaclassInfo<?>> {
	@Getter private final Class<T> metaclass;
	@Getter private Class<? extends AbstractType<?, ?>> mappedClass;
	@Getter private Class<? extends Core<?>> core;

	public MetaclassInfo(Class<T> metaclass) {
		this.metaclass = metaclass;
	}

	// true if this metaclass is a subtype of the other one (same direction as MappedLibraryTypeInfo)
	@Override
	public boolean specialices(MetaclassInfo<?> other) {
		return other.getMetaclass().isAssignableFrom(metaclass);
	}

	@Override
	public boolean isSpecilizedBy(Type element) {
		return metaclass.isInstance(element);
	}

	@Override
	public boolean canCreate(Type element) {
		return mappedClass != null && accepts(mappedClass, element);
	}

	@Override
	public AbstractType<?, ?> create(Type element, Mapper mapper) {
		return instantiate(mappedClass, core, element, mapper);
	}

	// a subclass of the mapped class replaces it; unrelated classes for the same metaclass are ambiguous
	public void setClass(Class<? extends AbstractType<?, ?>> aClass, Class<? extends Core<?>> core) {
		if (mappedClass != null && !mappedClass.isAssignableFrom(aClass)) {
			if (aClass.isAssignableFrom(mappedClass)) return;
			throw new IllegalStateException("Metaclass %s is mapped by unrelated classes %s and %s".formatted(metaclass.getSimpleName(), mappedClass.getName(), aClass.getName()));
		}
		this.mappedClass = aClass;
		this.core = core;
	}
}
