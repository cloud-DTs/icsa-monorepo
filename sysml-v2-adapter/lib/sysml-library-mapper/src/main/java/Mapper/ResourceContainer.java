package Mapper;

import lombok.Getter;
import lombok.Setter;
import org.eclipse.emf.ecore.resource.Resource;
import org.omg.sysml.interactive.SysMLInteractive;
import org.omg.sysml.lang.sysml.Element;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class ResourceContainer {


	@Getter private LibraryRawType libraryResources;
	@Getter private UserRawType userResources;


	public ResourceContainer(Collection<Resource> libraryResources, Collection<Resource> userResources) {
		this.libraryResources = new LibraryRawType(libraryResources);
		this.userResources = new UserRawType(userResources);
	}


	public boolean isPartOfLibraryResources(Element element) {
		return libraryResources.isPartOfRawType(element);
	}

	public  boolean isPartOfUserResources(Element element) {
		return userResources.isPartOfRawType(element);
	}

	public void updateUserResources(List<Resource> inputResources) {
		userResources = new UserRawType(inputResources);
	}
}
