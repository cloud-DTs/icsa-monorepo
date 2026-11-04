package SourceService.MappingRules;

import SourceService.SourceXMIElements.Element.EAElement;
import SourceService.SourceXMIElements.Mapper.Stereotypes;
import SourceService.XMIContext;
import model.*;
import org.json.JSONObject;
import registry.TwinRegistry;

import java.nio.file.Files;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Locale;

public class StrategyRule extends MappingRule<EAElement> {
    private static final String PATH_MAP_ENV = "DTP_PATH_MAP";

    public StrategyRule(XMIContext xmiContext, TwinRegistry twinRegistry) {
        super(xmiContext, twinRegistry);
    }

    @Override
    public boolean matches(EAElement element) {
        return element.getStereotypeName().equals(Stereotypes.STRATEGY_INSTANCE);
    }

    @Override
    public void apply(EAElement element) {
        EAElement strategyDefinition = getXmiContext().findDefinitonBlockForInstance(element);
        if (strategyDefinition == null) {
            throw new IllegalStateException("No StrategyDefinition found for instance: " + element.getName());
        }

        addStrategy(element, strategyDefinition);
    }

    public boolean isValidAndExists(String path) {
        try {
            Path p = Paths.get(path);
            return Files.exists(p);
        } catch (InvalidPathException e) {
            return false;
        }
    }

    private String resolvePathToCode(String path) {
        if (path == null || path.isEmpty() || isValidAndExists(path)) {
            return path;
        }

        String mappedPath = mapConfiguredPath(path);
        if (!mappedPath.equals(path) && isValidAndExists(mappedPath)) {
            return mappedPath;
        }

        return path;
    }

    private String mapConfiguredPath(String path) {
        return mapConfiguredPath(path, System.getenv(PATH_MAP_ENV));
    }

    static String mapConfiguredPath(String path, String pathMap) {
        if (path == null || pathMap == null || pathMap.isBlank()) {
            return path;
        }

        String normalizedPath = normalizePathPrefix(path);
        String bestSourcePrefix = null;
        String bestTargetPrefix = null;

        for (String mapping : pathMap.split(";")) {
            String[] parts = mapping.split("=", 2);
            if (parts.length != 2) {
                continue;
            }

            String sourcePrefix = normalizePathPrefix(parts[0].trim());
            String targetPrefix = normalizePathPrefix(parts[1].trim());
            if (sourcePrefix.isEmpty() || targetPrefix.isEmpty()) {
                continue;
            }

            boolean caseInsensitive = isWindowsPath(normalizedPath) && isWindowsPath(sourcePrefix);
            String comparablePath = caseInsensitive ? normalizedPath.toLowerCase(Locale.ROOT) : normalizedPath;
            String comparableSource = caseInsensitive ? sourcePrefix.toLowerCase(Locale.ROOT) : sourcePrefix;

            if (matchesPrefix(comparablePath, comparableSource)
                    && (bestSourcePrefix == null || sourcePrefix.length() > bestSourcePrefix.length())) {
                bestSourcePrefix = sourcePrefix;
                bestTargetPrefix = targetPrefix;
            }
        }

        if (bestSourcePrefix == null) {
            return path;
        }

        int relativeStart = bestSourcePrefix.length();
        if (relativeStart < normalizedPath.length() && normalizedPath.charAt(relativeStart) == '/') {
            relativeStart++;
        }

        String relativePath = normalizedPath.substring(relativeStart);
        if (relativePath.isEmpty()) {
            return bestTargetPrefix;
        }

        Path targetRoot = Paths.get(bestTargetPrefix).normalize();
        Path mappedPath = Paths.get(bestTargetPrefix, relativePath.split("/")).normalize();
        if (!mappedPath.startsWith(targetRoot)) {
            return path;
        }

        return mappedPath.toString();
    }

    private static boolean matchesPrefix(String path, String prefix) {
        if (path.equals(prefix)) {
            return true;
        }

        if (prefix.endsWith("/")) {
            return path.startsWith(prefix);
        }

        return path.startsWith(prefix + "/");
    }

    private static boolean isWindowsPath(String path) {
        return path.startsWith("//")
                || (path.length() >= 2 && Character.isLetter(path.charAt(0)) && path.charAt(1) == ':');
    }

    private static String normalizePathPrefix(String path) {
        String normalized = path.replace('\\', '/');
        while (normalized.length() > 1
                && normalized.endsWith("/")
                && !isWindowsDriveRoot(normalized)) {
            normalized = normalized.substring(0, normalized.length() - 1);
        }
        return normalized;
    }

    private static boolean isWindowsDriveRoot(String path) {
        return path.length() == 3
                && Character.isLetter(path.charAt(0))
                && path.charAt(1) == ':'
                && path.charAt(2) == '/';
    }


    private void addStrategy(EAElement element, EAElement strategyDefinition) {
        TwinStrategy twinStrategy = new TwinStrategy();
        String pathToCode = resolvePathToCode(getXmiContext().getTaggedValue(strategyDefinition, "pathToCode"));
        if(!pathToCode.isEmpty()){
            if(!isValidAndExists(pathToCode)){
                throw new IllegalStateException("Strategy " + strategyDefinition.getName() + " code not found: " + pathToCode
                        + ". Configure " + PATH_MAP_ENV + " to rewrite host paths to container paths.");
            }
        }
        twinStrategy.setPathToCode(pathToCode);
        twinStrategy.setStrategyType(getXmiContext().getTaggedValue(strategyDefinition, "type").toLowerCase());
        twinStrategy.setStrategyId(element.getIdref());
        twinStrategy.setName(element.getName());
        twinStrategy.setDefinitionId(strategyDefinition.getIdref());
        FeedBack feedBack = initFeedBack(element);
        twinStrategy.setFeedBack(feedBack);
        getTwinRegistry().registerStrategy(element.getIdref(), twinStrategy);
    }

    private FeedBack initFeedBack(EAElement element) {
        String topicType = getXmiContext().getTaggedValue(element,"feedBackTopicType");
        String payloadType = getXmiContext().getTaggedValue(element, "feedBackPayloadType");
        String payload = getXmiContext().getTaggedValue(element,"customPayload");
        String topic = getXmiContext().getTaggedValue(element,"customTopic");
        return getFeedBack(topicType,payloadType,payload,topic);
    }

    private FeedBack getFeedBack(String topicType, String payloadType,String customPayload,String customTopic) {

        switch (topicType){
            case "INTERNAL" -> {
                InternalFeedBackTopic internalFeedBackTopic = new InternalFeedBackTopic();
                internalFeedBackTopic.setPayload(getPayload(payloadType,customPayload));
                return  internalFeedBackTopic;
            }
            case "EXTERNAL" -> {
                ExternalFeedBackTopic externalFeedBackTopic = new ExternalFeedBackTopic();
                externalFeedBackTopic.setTopic(customTopic);
                externalFeedBackTopic.setPayload(getPayload(payloadType,customPayload));
                return externalFeedBackTopic;

            }
            case "NONE" -> {
                return new NoneFeedBackTopic();
            }
            default -> throw new IllegalStateException("Unexpected FeedBackTopicType: " + topicType);
        }
    }

    private Payload getPayload(String payloadType,String customPayload) {
        switch (payloadType){
            case "custom" -> {
                CustomPayload payload = new CustomPayload();
                JSONObject jsonObject = new JSONObject(customPayload);
                payload.setPayload(jsonObject);
                return payload;
            }
            case "strategyResult" -> {
                ActionResultPayload actionResultPayload = new ActionResultPayload();
                actionResultPayload.setPayload("action-result");
                return actionResultPayload;
            }
            default -> throw new IllegalStateException("Unexpected payloadType: " + payloadType);
        }
    }
}

