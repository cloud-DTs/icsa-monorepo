package Main;



import Model.AbstractType;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public class ResultConverter {
	private TwinDataBase twinDataBase;
	public ResultConverter(TwinDataBase twinDataBase) {
		this.twinDataBase = twinDataBase;
	}

	public TwinDataBase getTwinDataBase() {
		return twinDataBase;
	}


	public List<AbstractType<?,?>> getAll() {
		return List.copyOf(twinDataBase.getElements().values());
	}

	public Optional<AbstractType<?,?>> getById(UUID id) {
		return Optional.ofNullable(twinDataBase.getElements().get(id));
	}

	public <T extends AbstractType<?,?>> Optional<T> getById(UUID id, Class<T> type) {
		return getById(id).filter(type::isInstance).map(type::cast);
	}

	public <T extends AbstractType<?,?>> List<T> getByType(Class<T> type) {
		return twinDataBase.getElements().values().stream().filter(type::isInstance).map(type::cast).toList();
	}
}
