package org.example;

import Executor.SemanticException;
import Main.ResultConverter;
import Main.SysmlConverterMain;
import org.example.Rules.DTRuleExecutor;

import java.io.IOException;

// entry point: parses models against the DigitalTwinLibrary
public class DTLibraryParser {

	private static final String LIBRARY_ZIP = "DTLibrary.zip";

	private final SysmlConverterMain sysmlConverterMain;

	public DTLibraryParser() throws IOException {
		sysmlConverterMain = new SysmlConverterMain(LIBRARY_ZIP, new DTRuleExecutor());
	}

	public ResultConverter parse(String... paths) throws SemanticException {
		return sysmlConverterMain.parse(paths);
	}
}
