package Mapper;

import Model.AbstractType;
import Model.Core.Core;
import org.omg.sysml.lang.sysml.Type;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.List;

public interface MappedComprable<T extends Type, C extends MappedComprable<?, C>> {

	boolean specialices(C other);

	boolean isSpecilizedBy(Type element);

	boolean canCreate(Type element);

	AbstractType<?, ?> create(Type element, Mapper mapper);

	default AbstractType<?, ?> instantiate(Class<? extends AbstractType<?, ?>> mappedClass, Class<? extends Core<?>> coreClass, Type element, Mapper mapper) {
		try {
			AbstractType<?, ?> created = mappedClass.cast(findConstructor(mappedClass, element.getClass()).newInstance(element, mapper));
			Object core = findConstructor(coreClass, element.getClass()).newInstance(element, mapper);
			Field coreField = AbstractType.class.getDeclaredField("core");
			coreField.setAccessible(true);
			coreField.set(created, core);
			return created;
		} catch (ReflectiveOperationException e) {
			throw new IllegalStateException("Failed to create %s with core %s for element '%s'"
					.formatted(mappedClass.getSimpleName(), coreClass.getSimpleName(), element.getName()), e);
		}
	}

	default boolean accepts(Class<?> aClass, Type element) {
		return Arrays.stream(aClass.getConstructors())
				.anyMatch(x -> x.getParameterCount() == 2 && x.getParameterTypes()[0].isInstance(element) && x.getParameterTypes()[1].isAssignableFrom(Mapper.class));
	}

	default Constructor<?> findConstructor(Class<?> aClass, Class<? extends Type> elementClass) {
		List<Constructor<?>> valid = Arrays.stream(aClass.getConstructors())
				.filter(x -> x.getParameterCount() == 2)
				.filter(x -> x.getParameterTypes()[0].isAssignableFrom(elementClass) && x.getParameterTypes()[1].isAssignableFrom(Mapper.class))
				.toList();

		if (valid.size() != 1) {
			throw new IllegalStateException("Expected exactly one constructor (element, Mapper) in class %s for type %s, but found %d"
					.formatted(aClass.getName(), elementClass.getName(), valid.size()));
		}
		return valid.getFirst();
	}
}
