package TargetService;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.io.IOException;
import java.nio.file.Path;
import java.util.Set;

/**
 * Research prototype: removes the identifiers of the Enterprise Architect elements from the
 * generated files. The deployer rejects unknown keys and does not use these identifiers.
 */
public final class DeployerCleaner {

    static final Set<String> CONFIG_KEYS = Set.of(
            "hot_storage_id", "hot_storage_definition_id",
            "cold_storage_id", "cold_storage_definition_id");
    static final Set<String> HIERARCHY_KEYS = Set.of("definitionId");

    private DeployerCleaner() {
    }

    /** Cleans config.json and config_hierarchy.json in the folder of one twin. */
    public static void clean(Path twinDir, ObjectMapper mapper) throws IOException {
        strip(twinDir.resolve("config.json"), CONFIG_KEYS, mapper);
        strip(twinDir.resolve("config_hierarchy.json"), HIERARCHY_KEYS, mapper);
    }

    private static void strip(Path file, Set<String> keys, ObjectMapper mapper) throws IOException {
        JsonNode root = mapper.readTree(file.toFile());
        int removed = remove(root, keys);
        mapper.writerWithDefaultPrettyPrinter().writeValue(file.toFile(), root);
        System.out.println("Cleaned " + file.getFileName() + ": removed " + removed + " key(s)");
    }

    static int remove(JsonNode node, Set<String> keys) {
        int removed = 0;
        if (node instanceof ObjectNode object) {
            for (String key : keys) {
                if (object.remove(key) != null) {
                    removed++;
                }
            }
        }
        for (JsonNode child : node) {
            removed += remove(child, keys);
        }
        return removed;
    }
}
