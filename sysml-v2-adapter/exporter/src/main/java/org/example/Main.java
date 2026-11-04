package org.example;

import Executor.SemanticException;
import Main.ResultConverter;
import Model.AbstractType;
import com.fasterxml.jackson.core.util.DefaultIndenter;
import com.fasterxml.jackson.core.util.DefaultPrettyPrinter;
import com.fasterxml.jackson.core.util.Separators;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectWriter;
import com.fasterxml.jackson.databind.node.ArrayNode;
import org.example.Model.Twin.TwinCoreApi;
import org.example.Model.Twin.TwinDefinition;
import org.example.Model.Twin.TwinUsage;


import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;

public class Main {

	private static final int MAX_TWIN_NAME_LENGTH = 10;


	public static void main(String[] args) throws IOException, SemanticException {
		if (args.length < 2) {
			throw new IllegalArgumentException("Usage: <outputDir> <sysml file or directory>... (at least one model path is required)");
		}
		Path outputDir = Path.of(args[0]);
		String[] modelPaths = Arrays.copyOfRange(args, 1, args.length);

		ResultConverter result = new DTLibraryParser().parse(modelPaths);

		ObjectMapper json = new ObjectMapper();
		ObjectWriter writer = json.writer(prettyPrinter());
		TwinExporter exporter = new TwinExporter(json, new ShortUuid(), new ConstValue());

		List<AbstractType<?, ?>> twins = Stream.concat(result.getByType(TwinDefinition.class).stream(), result.getByType(TwinUsage.class).stream())
				.filter(twin -> !twin.isLibrary() && twin.getParent().isEmpty())
				.<AbstractType<?, ?>>map(twin -> twin)
				.filter(Main::hasValidName)
				.toList();

		ArrayNode index = json.createArrayNode();
		for (AbstractType<?, ?> twin : twins) {
			String id = exporter.id(twin);
			Path twinDir = outputDir.resolve(id);
			Files.createDirectories(twinDir);
			TwinCoreApi api = TwinCoreApi.class.cast(twin);
			write(writer, twinDir.resolve("config.json"), exporter.config(twin.getName(), api));
			write(writer, twinDir.resolve("config_hierarchy.json"), exporter.hierarchy(api));
			write(writer, twinDir.resolve("config_events.json"), exporter.events(api));
			write(writer, twinDir.resolve("config_iot_devices.json"), exporter.iotDevices(api));
			index.addObject().put("name", twin.getName()).put("id", id).put("folder", id);
			System.out.println("Generated twin " + twin.getName() + " in " + twinDir);
		}
		Files.createDirectories(outputDir);
		write(writer, outputDir.resolve("twins.json"), index);

		if (twins.isEmpty()) {
			System.err.println("Error: no digital twin generated (none found or all names longer than " + MAX_TWIN_NAME_LENGTH + " characters)");
			System.exit(1);
		}
	}

	private static boolean hasValidName(AbstractType<?, ?> twin) {
		if (twin.getName().length() <= MAX_TWIN_NAME_LENGTH) return true;
		System.err.println("Warning: twin '%s' is longer than %d characters and is skipped".formatted(twin.getName(), MAX_TWIN_NAME_LENGTH));
		return false;
	}



	private static void write(ObjectWriter writer, Path file, JsonNode content) throws IOException {
		writer.writeValue(file.toFile(), content);
	}


	private static DefaultPrettyPrinter prettyPrinter() {
		DefaultIndenter indenter = new DefaultIndenter("    ", "\n");
		Separators separators = Separators.createDefaultInstance().withObjectFieldValueSpacing(Separators.Spacing.AFTER);
		return new DefaultPrettyPrinter(separators).withObjectIndenter(indenter).withArrayIndenter(indenter);
	}
}
