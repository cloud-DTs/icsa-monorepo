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
        String pathMap = System.getenv(PATH_MAP_ENV);
        if (pathMap == null || pathMap.isBlank()) {
            return path;
        }

        for (String mapping : pathMap.split(";")) {
            String[] parts = mapping.split("=", 2);
            if (parts.length != 2) {
                continue;
            }

            String sourcePrefix = normalizePathPrefix(parts[0].trim());
            String targetPrefix = parts[1].trim();
            String normalizedPath = normalizePathPrefix(path);

            if (normalizedPath.equals(sourcePrefix)) {
                return targetPrefix;
            }

            if (normalizedPath.startsWith(sourcePrefix + "/")) {
                String relativePath = normalizedPath.substring(sourcePrefix.length() + 1);
                return Paths.get(targetPrefix, relativePath.split("/")).normalize().toString();
            }
        }

        return path;
    }

    private String normalizePathPrefix(String path) {
        return path.replace('\\', '/').replaceAll("/+$", "");
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

