package Mapper;

import lombok.Getter;
import org.eclipse.emf.common.util.TreeIterator;
import org.eclipse.emf.common.util.URI;
import org.eclipse.emf.ecore.EObject;
import org.eclipse.emf.ecore.resource.Resource;
import org.omg.sysml.lang.sysml.Element;

import java.util.*;

public abstract class RawType {

	protected Collection<Resource> resource;

	@Getter
	protected List<Element> rootElement = new ArrayList<>();

	private Set<URI> uris = new HashSet<>();

	RawType(Collection<Resource> resources) {
		this.resource = resources;

		for (Resource resource : resources) {
			uris.add(resource.getURI());
			rootElement.add(NewUtil.getRootElementFromResource(resource));
		}
	}


	public boolean isPartOfRawType(Element element) {
		if (element == null || element.eResource() == null) {
			return false;
		}
		return uris.contains(element.eResource().getURI());
	}


	public Collection<Element> getAllElements() {
		return collectElementsFromResource(resource.stream().toList());
	}

	private List<Element> collectElementsFromResource(Resource resource) {
		List<Element> elements = new ArrayList<>();
		TreeIterator<EObject> iterator = resource.getAllContents();
		while (iterator.hasNext()) {
			EObject eObject = iterator.next();
			if (eObject instanceof Element element) {
				elements.add(element);
			}
		}
		return elements;
	}

	private List<Element> collectElementsFromResource(Collection<Resource> resource) {
		List<Element> elements = new ArrayList<>();
		for (Resource res : resource) {
			elements.addAll(collectElementsFromResource(res));
		}
		return elements;
	}
}
