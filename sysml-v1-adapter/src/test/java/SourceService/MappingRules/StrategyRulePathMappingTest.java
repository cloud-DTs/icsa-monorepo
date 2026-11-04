package SourceService.MappingRules;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class StrategyRulePathMappingTest {

    @Test
    void mapsWindowsPathsCaseInsensitively() {
        String mapped = StrategyRule.mapConfiguredPath(
                "c:\\code\\handler.py",
                "C:/Code=/pipeline/code"
        );

        assertEquals("/pipeline/code/handler.py", withForwardSlashes(mapped));
    }

    @Test
    void selectsTheMostSpecificMappingRegardlessOfOrder() {
        String mapped = StrategyRule.mapConfiguredPath(
                "C:\\Code\\handler.py",
                "C:/=/pipeline/root;C:/Code=/pipeline/code"
        );

        assertEquals("/pipeline/code/handler.py", withForwardSlashes(mapped));
    }

    @Test
    void keepsPosixPathMatchingCaseSensitive() {
        String original = "/opt/Code/handler.py";

        assertEquals(
                original,
                StrategyRule.mapConfiguredPath(original, "/opt/code=/pipeline/code")
        );
    }

    @Test
    void ignoresMalformedOrEmptyMappings() {
        String original = "C:\\Code\\handler.py";

        assertEquals(
                original,
                StrategyRule.mapConfiguredPath(original, "broken;=;/source=")
        );
    }

    @Test
    void preventsMappingsFromEscapingTheTargetRoot() {
        String original = "C:/Code/../secret.py";

        assertEquals(
                original,
                StrategyRule.mapConfiguredPath(original, "C:/Code=/pipeline/code")
        );
    }

    private static String withForwardSlashes(String path) {
        return path.replace('\\', '/');
    }
}
