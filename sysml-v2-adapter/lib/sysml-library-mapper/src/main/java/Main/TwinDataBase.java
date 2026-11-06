package Main;

import Model.AbstractType;
import lombok.Getter;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

public class TwinDataBase {

	@Getter private final Map<UUID, AbstractType<?,?>> elements = new LinkedHashMap<>();

	public TwinDataBase(Collection<? extends AbstractType<?,?>> elements) {
		for (AbstractType<?,?> m : elements) {
			this.elements.put(m.getId(), m);
		}
	}


}