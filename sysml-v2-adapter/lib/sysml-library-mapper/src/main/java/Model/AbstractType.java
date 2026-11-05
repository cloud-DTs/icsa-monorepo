package Model;


import Mapper.Mapper;
import Model.Core.Core;
import Model.Core.CoreApi;
import lombok.Getter;
import lombok.Setter;

import java.util.Arrays;
import java.util.Optional;
import java.util.UUID;

public abstract class AbstractType<T extends org.omg.sysml.lang.sysml.Type, C extends Core<? super T>> implements CoreApi<C> {

	// set by the parser right after construction, from the core named in the mapping annotation
	private C core;


	protected Mapper instance;

	@Getter
	protected T sysmlElement;

	@Getter
	private final String name;

	@Getter
	@Setter
	private UUID id;

	@Getter
	@Setter
	protected boolean isInherited;

	@Getter
	private Optional<AbstractType<?,?>> parent = Optional.empty();




	public AbstractType(T sysmlElement, Mapper mapper) {
		this.sysmlElement = sysmlElement;
		this.name = sysmlElement.getName();
		this.instance = mapper;

	}

	@Getter
	@Setter
	protected boolean isLibrary = false;

	public void setParent(AbstractType<?,?> parent) {
		if (parent != null && this.parent.isEmpty()) {
			this.parent = Optional.of(parent);
		}
	}


	public void fillSlots() { getCore().fillSlots(this); }

	@Override
	public C getCore() {
		return core;
	}


}
