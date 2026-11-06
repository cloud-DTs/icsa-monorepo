package Main;

import org.eclipse.emf.ecore.resource.Resource;
import org.omg.sysml.interactive.SysMLInteractive;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;

public class ReadManagerTwo {

	// extracts a zip from the classpath (e.g. "DTLibrary.zip") into a temporary directory
	public static Path extractStandardLibrary(String zipResourceName) throws IOException {
		Path tempDirectory = Files.createTempDirectory(zipResourceName.replace(".zip", "") + "_temp");
		try (var input = ReadManagerTwo.class.getClassLoader().getResourceAsStream(zipResourceName)) {
			if (input == null) {
				throw new IllegalStateException("Library zip '%s' not found on the classpath.".formatted(zipResourceName));
			}
			try (var zip = new java.util.zip.ZipInputStream(input)) {
				java.util.zip.ZipEntry entry;
				while ((entry = zip.getNextEntry()) != null) {
					Path destination = tempDirectory.resolve(entry.getName()).normalize();
					if (!destination.startsWith(tempDirectory)) {
						throw new IOException("Invalid ZIP entry: " + entry.getName());
					}
					if (entry.isDirectory()) {
						Files.createDirectories(destination);
					} else {
						Files.createDirectories(destination.getParent());
						Files.copy(zip, destination, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
					}
					zip.closeEntry();
				}
			}
		}
		return tempDirectory;
	}


	public static List<Resource> readAllInput(SysMLInteractive sysMLInteractive,String path, String extension) {
		sysMLInteractive.readAll(path,true,extension);
		return sysMLInteractive.getInputResources();
	}

	public static List<Resource> readAllLibrary(SysMLInteractive s, String path, String ext) {
		Set<Resource> before = Set.copyOf(s.getResourceSet().getResources());   // std lib is in here
		s.readAll(path, false, ext);
		return s.getResourceSet().getResources().stream()
				.filter(r -> !before.contains(r))                              // only what this call added
				.toList();
	}
}
