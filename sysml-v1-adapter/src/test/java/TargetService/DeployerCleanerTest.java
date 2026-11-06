package TargetService;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DeployerCleanerTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void removesTheIdentifiersFromConfigAndHierarchy(@TempDir Path dir) throws Exception {
        Files.writeString(dir.resolve("config.json"), """
                {"digital_twin_name": "t", "hot_storage_size_in_days": 30, "hot_storage_id": "a",
                 "hot_storage_definition_id": "b", "cold_storage_size_in_days": 60,
                 "cold_storage_id": "c", "cold_storage_definition_id": "d"}
                """);
        Files.writeString(dir.resolve("config_hierarchy.json"), """
                [{"id": "1", "definitionId": "x", "name": "n", "type": "entity",
                  "children": [{"id": "2", "definitionId": "y", "name": "m", "type": "component"}]}]
                """);

        DeployerCleaner.clean(dir, mapper);

        JsonNode config = mapper.readTree(dir.resolve("config.json").toFile());
        assertEquals(3, config.size());
        assertEquals(30, config.get("hot_storage_size_in_days").asInt());
        assertEquals(60, config.get("cold_storage_size_in_days").asInt());

        JsonNode hierarchy = mapper.readTree(dir.resolve("config_hierarchy.json").toFile());
        assertFalse(hierarchy.toString().contains("definitionId"));
        assertTrue(hierarchy.get(0).get("children").get(0).has("id"));
    }
}
