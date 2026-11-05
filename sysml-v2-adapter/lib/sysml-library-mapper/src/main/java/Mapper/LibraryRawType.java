package Mapper;

import lombok.Getter;
import org.eclipse.emf.ecore.resource.Resource;
import org.omg.sysml.lang.sysml.Element;
import org.omg.sysml.lang.sysml.Type;
import org.omg.sysml.lang.sysml.util.SysMLLibraryUtil;

import java.util.Collection;
import java.util.HashMap;
import java.util.Map;

@Getter
public class LibraryRawType extends RawType {

	@Getter private Map<String, Type> libraries = new HashMap<String, Type>();

	LibraryRawType(Collection<Resource> resources) {
		super(resources);

	}


	public Type getLibraryType(String libraryNameSpaces) {

		if (this.libraries.containsKey(libraryNameSpaces)) {
			return libraries.get(libraryNameSpaces);
		}
		for (Element rootElement : rootElement) {
			if (SysMLLibraryUtil.getLibraryType(rootElement, String.valueOf(libraryNameSpaces)) != null) {
				libraries.put(libraryNameSpaces, SysMLLibraryUtil.getLibraryType(rootElement, String.valueOf(libraryNameSpaces)));
				break;
			}
		}
		return  libraries.get(libraryNameSpaces);
	}




}
