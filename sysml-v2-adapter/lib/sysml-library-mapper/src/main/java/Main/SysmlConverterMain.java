package Main;

import Executor.Executor;
import Mapper.Mapper;
import Mapper.NewUtil;
import Mapper.ResourceContainer;
import lombok.extern.slf4j.Slf4j;
import org.apache.logging.log4j.core.config.Configurator;
import org.eclipse.emf.common.util.URI;
import org.eclipse.emf.ecore.resource.Resource;
import org.eclipse.xtext.resource.IResourceServiceProvider;
import org.eclipse.xtext.resource.impl.ResourceDescriptionsData;
import org.eclipse.xtext.util.CancelIndicator;
import org.eclipse.xtext.validation.CheckMode;
import org.eclipse.xtext.validation.IResourceValidator;
import org.eclipse.xtext.validation.Issue;
import Executor.DefaultRuleExecutor;
import Executor.SemanticException;
import Mapper.Scanner;
import org.omg.sysml.interactive.SysMLInteractive;
import org.slf4j.event.Level;

import java.io.IOException;
import java.util.*;

@Slf4j
public class SysmlConverterMain {

	private static final String STANDARD_LIBRARY_ZIP = "sysml_library.zip";
	// zip of the domain library on the classpath, given by the project that uses the parser
	private final String libraryZip;
	private final Map<URI, Resource> uriToResourceMap = new HashMap<>();
	private SysMLInteractive sysMLInteractive;
	private ResultConverter result;
	private Collection<Resource> libraryResources;
	protected Scanner scanner;
	private Executor executor = new DefaultRuleExecutor();
	protected NewUtil newUtil;


	public SysmlConverterMain(String libraryZip, Executor executor) throws IOException {
		this.libraryZip = libraryZip;
		this.executor = executor;
		init();
	}

	public SysmlConverterMain(String libraryZip) throws IOException {
		this.libraryZip = libraryZip;
		init();
	}

	private void init() throws IOException {
		initSysMLInteractive();
		initStandardLibrary();
		initLibrary();
		newUtil = new NewUtil(new ResourceContainer(libraryResources, sysMLInteractive.getInputResources()));
		scanner = new Scanner(newUtil);
	}

	private void initSysMLInteractive() throws IOException {
		sysMLInteractive = SysMLInteractive.createInstance();
	}
	private void initStandardLibrary() throws IOException {
		sysMLInteractive.loadLibrary(ReadManagerTwo.extractStandardLibrary(STANDARD_LIBRARY_ZIP).toString());
	}

	private void initLibrary() throws IOException {
		String libraryPath = ReadManagerTwo.extractStandardLibrary(libraryZip).toString();
		libraryResources = List.copyOf(ReadManagerTwo.readAllLibrary(sysMLInteractive, libraryPath, ".sysml"));
		validateAllAndThrowIfInvalid(libraryResources);
	}

	public synchronized ResultConverter parse(String ... path) throws SemanticException {
		removeAllInputResources();
		parseUserResources(path);
		map();
		log.info("Parsing completed successfully.");
		return result;
	}

	private void parseUserResources(String[] path) {
		for (String p : path) {
			List<Resource> resources = ReadManagerTwo.readAllInput(sysMLInteractive,p,".sysml");
			for (Resource resource : resources) {
				uriToResourceMap.put(resource.getURI(), resource);
			}

		}
		validateAllAndThrowIfInvalid(uriToResourceMap.values());
	}

	private void map() throws SemanticException {
		newUtil.getResourceContainer().updateUserResources(sysMLInteractive.getInputResources());
		Mapper mapper = getMapper();
		executor.executeGeneralRules(newUtil);
		mapper.parse();
		result = new ResultConverter(new TwinDataBase(mapper.getMapperMap().values()));
		executor.executeSemanticRules(newUtil,result);

	}

	private void removeAllInputResources() {
		ResourceDescriptionsData index = ResourceDescriptionsData.ResourceSetAdapter
				.findResourceDescriptionsData(sysMLInteractive.getResourceSet());
		for (Resource resource : new ArrayList<>(sysMLInteractive.getInputResources())) {
			index.removeDescription(resource.getURI());
			resource.unload();
			sysMLInteractive.getResourceSet().getResources().remove(resource);
		}
		sysMLInteractive.getInputResources().clear();
		uriToResourceMap.clear();
	}

	private List<Issue> validate(Resource resource) {
		IResourceValidator validator = IResourceServiceProvider.Registry.INSTANCE
				.getResourceServiceProvider(resource.getURI())
				.getResourceValidator();

		return validator.validate(resource, CheckMode.ALL, CancelIndicator.NullImpl);
	}

	private List<Issue> validateAll(Collection<Resource> resources) {
		List<Issue> allIssues = new ArrayList<>();
		for (Resource resource : resources) {
			allIssues.addAll(validate(resource));
		}
		return allIssues;
	}
	private void validateAllAndThrowIfInvalid(Collection<Resource> resources) {
		List<Issue> allIssues = validateAll(resources);
		if (!allIssues.isEmpty()) {
			throw new IllegalStateException("Validation failed with issues: " + allIssues);
		}
	}





	protected Mapper getMapper() {
		return new Mapper(scanner, newUtil);
	}



}
