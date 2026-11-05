package Model;

import Mapper.Mapper;
import org.omg.sysml.lang.sysml.Type;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Optional;


public final class Slots {

	private Slots() {
	}

	@SuppressWarnings("unchecked")
	public static <T> Class<T> rawClassOf(Class<?> rawClass) {
		return (Class<T>) rawClass;
	}

	public static <T> Optional<T> atMostOne(AbstractType<?,?> owner, String slotName, List<T> values) {
		if (values.size() > 1) {
			throw new IllegalStateException("'%s': slot '%s' may be specified at most once, but found %d."
					.formatted(owner.getName(), slotName, values.size()));
		}
		return values.stream().findFirst();
	}

	public static <T> T exactlyOne(AbstractType<?,?> owner, String slotName, List<T> values) {
		if (owner.isLibrary() && values.isEmpty()) {
			return null;
		}
		if (values.size() != 1) {
			throw new IllegalStateException("'%s': slot '%s' is required exactly once, but found %d."
					.formatted(owner.getName(), slotName, values.size()));
		}
		return values.getFirst();
	}

	public static <T> List<T> mapAll(Mapper mapper, AbstractType<?,?> owner, Collection<? extends Type> elements, Class<T> type) {
		List<T> result = new ArrayList<>();
		for (Type element : elements) {
			AbstractType<?,?> mapped = mapper.map(element, owner);
			if (type.isInstance(mapped)) result.add(type.cast(mapped));
		}
		return result;
	}
}

