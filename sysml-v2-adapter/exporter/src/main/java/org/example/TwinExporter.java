package org.example;

import Model.AbstractType;
import Model.Predefined.MetaClasses.Expression.LiteralUsage;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.example.Model.Attribute.ConstAttributeUsage;
import org.example.Model.Attribute.MeasureAttributeUsage;
import org.example.Model.Attribute.MeasureReferenceUsage;
import org.example.Model.Attribute.TwinAttributeUsage;
import org.example.Model.Component.ComponentDefinition;
import org.example.Model.Component.ComponentUsage;
import org.example.Model.Condition.ConditionUsage;
import org.example.Model.Entity.EntityUsage;
import org.example.Model.Enums.EnumAttributeDataType;
import org.example.Model.Enums.EnumComparisonOperator;
import org.example.Model.Enums.EnumFeedbackTopicType;
import org.example.Model.Strategy.StrategyActionUsage;
import org.example.Model.Twin.TwinCoreApi;

import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.stream.Collectors;

public class TwinExporter {

	private static final int DEFAULT_RETENTION_DAYS = 30;
	private static final String CONST_COMPONENT_SUFFIX = "const_component";
	private static final Map<EnumComparisonOperator, String> OPERATOR_SYMBOLS = Map.of(
			EnumComparisonOperator.GREATER_THAN, ">",
			EnumComparisonOperator.LESS_THAN, "<",
			EnumComparisonOperator.EQUAL, "==",
			EnumComparisonOperator.GREATER_EQUAL, ">=",
			EnumComparisonOperator.LESS_EQUAL, "<=",
			EnumComparisonOperator.NOT_EQUAL, "!=");

	private final ObjectMapper json;
	private final ShortUuid shortUuid;
	private final ConstValue constValue;




	public TwinExporter(ObjectMapper json, ShortUuid shortUuid, ConstValue constValue) {
		this.json = json;
		this.shortUuid = shortUuid;
		this.constValue = constValue;
	}

	public String id(AbstractType<?, ?> element) {
		return id(element.getId());
	}

	public String id(UUID uuid) {
		return shortUuid.encode(uuid);
	}

	public String id(String uuid) {
		return shortUuid.encode(UUID.fromString(uuid));
	}




	public ObjectNode config(String twinName, TwinCoreApi twin) {
		ObjectNode node = json.createObjectNode();
		node.put("digital_twin_name", twinName);
		node.put("hot_storage_size_in_days", retention(twin.getHotDatabaseRetentionDays()));
		node.put("cold_storage_size_in_days", retention(twin.getColdDatabaseRetentionDays()));
		return node;
	}


	public ArrayNode hierarchy(TwinCoreApi twin) {
		ArrayNode result = json.createArrayNode();
		twin.getEntities().forEach(entity -> result.add(entityHierarchy(entity)));
		return result;
	}


	private Set<String> schema(List<? extends MeasureAttributeUsage<?, ?>> attrs) {
		return attrs.stream().map(a -> {
			if (a.getName() == null) throw new IllegalArgumentException(
					"Unnamed attribute in '%s'".formatted(a.getParent().map(AbstractType::getName).orElse("?")));
			return a.getName() + ":" + dataType(a);
		}).collect(Collectors.toSet());
	}

	public ArrayNode iotDevices(TwinCoreApi twin) {
		ArrayNode result = json.createArrayNode();
		twin.getEntities().forEach(entity -> addIotDevices(entity, result));
		return result;
	}


	public ArrayNode events(TwinCoreApi twin) {
		ArrayNode result = json.createArrayNode();
		for (ConditionUsage condition : twin.getConditions()) {
			System.out.println(condition.getName());

			String expression = "%s %s %s".formatted(
					operandChain(condition, condition.getLeftOperand(), "leftOperand"),
					OPERATOR_SYMBOLS.get(condition.getOperator().flatMap(o -> o.getValue()).orElse(EnumComparisonOperator.EQUAL)),
					operandChain(condition, condition.getRightOperand(), "rightOperand"));
			if(condition.getStrategyActions().isEmpty()){
				throw new IllegalArgumentException("Condition '%s' has no strategy actions.".formatted(condition.getName()));
			}
			for (StrategyActionUsage action : condition.getStrategyActions()) {
				ObjectNode event = result.addObject();
				event.put("condition", expression);
				event.set("action", action(action));
			}
		}
		return result;
	}
	private Optional<ComponentDefinition> sharedDef(ComponentUsage c) {
		return c.getDefinition().filter(def -> schema(def.getMeasurements()).equals(schema(c.getMeasurements())));
	}
	private String componentTypeId(ComponentUsage c)   { return sharedDef(c).map(this::id).orElse(id(c)); }
	private String componentTypeName(ComponentUsage c) { return sharedDef(c).map(AbstractType::getName).orElse(c.getName()); }

	private ObjectNode entityHierarchy(EntityUsage entity) {
		ObjectNode node = json.createObjectNode();
		node.put("id", id(entity));
		node.put("type", "entity");
		node.put("name", entity.getName());
		ArrayNode children = node.putArray("children");
		entity.getEntities().forEach(sub -> children.add(entityHierarchy(sub)));
		for (ComponentUsage component : entity.getComponents()) {
			children.addObject()
					.put("type", "component").put("name", component.getName())
					.put("iotDeviceId", id(component)).put("componentTypeId", componentTypeId(component)).put("componentTypeName", componentTypeName(component));
		}
		if (!entity.getConstAttributes().isEmpty()) {
			children.addObject().put("iotDeviceId", constComponentId(entity))
					.put("type", "component")
					.put("name", entity.getName() + CONST_COMPONENT_SUFFIX)
					.put("componentTypeId", constComponentTypeId(entity));
		}
		return node;
	}

	private void addIotDevices(EntityUsage entity, ArrayNode result) {
		entity.getEntities().forEach(sub -> addIotDevices(sub, result));
		for (ComponentUsage component : entity.getComponents()) {
			ObjectNode device = result.addObject();
			device.put("id", id(component));
			ArrayNode properties = device.putArray("properties");
			component.getMeasurements().forEach(attribute -> properties.add(attributeNode(attribute, "initValue")));
		}
		if (!entity.getConstAttributes().isEmpty()) {
			ObjectNode device = result.addObject();
			device.put("id", constComponentId(entity));
			ArrayNode properties = device.putArray("properties");
			entity.getConstAttributes().forEach(attribute -> properties.add(attributeNode(attribute, "initValue")));
		}
	}

	private ObjectNode attributeNode(MeasureAttributeUsage<?, ?> attribute, String valueKey) {
		ObjectNode node = json.createObjectNode();
		node.put("name", attribute.getName());
		String dataType = dataType(attribute);
		node.put("dataType", dataType);
		if (ConstAttributeUsage.class.isInstance(attribute)) {
			literal(ConstAttributeUsage.class.cast(attribute).getValue())
					.ifPresent(raw -> node.set(valueKey, constValue.convert(attribute.getName(), dataType, String.valueOf(raw))));
		}
		return node;
	}

	private ObjectNode action(StrategyActionUsage action) {
		ObjectNode node = json.createObjectNode();
		node.put("type", action.getStrategyType().getValue().orElseThrow().getStringRepresentation().toLowerCase());
		node.put("pathToCode", String.valueOf(literal(Optional.of(action.getPathToCode())).orElseThrow()));
		node.put("functionName", action.getName());
		node.put("external", Boolean.TRUE.equals(literal(Optional.of(action.getExternal())).orElse(false)));

		EnumFeedbackTopicType feedbackType = action.getFeedbackTopicType().flatMap(f -> f.getValue()).orElse(EnumFeedbackTopicType.NOFEEDBACK);
		if (feedbackType != EnumFeedbackTopicType.NOFEEDBACK) {
			ObjectNode feedback = node.putObject("feedback");
			feedback.put("type", "mqtt");
			action.getComponentTopic().flatMap(topic -> topic.getReference()).ifPresent(component -> feedback.put("iotDeviceId", id(component)));
			literal(action.getExternalTopic()).map(String::valueOf).filter(topic -> !topic.isEmpty()).ifPresent(topic -> feedback.put("topic", topic));
			Optional<JsonNode> payload = literal(action.getCustomPayload()).map(String::valueOf).map(raw -> parsePayload(action, raw));
			feedback.set("payload", payload.orElse(json.getNodeFactory().textNode("action-result")));
		}

		node.set("inputParameters", parameters(action, action.getInputParameters(), "inputParameters"));
		node.set("outputParameters", parameters(action, action.getOutputParameters(), "outputParameters"));
		return node;
	}

	private ArrayNode parameters(StrategyActionUsage action, List<? extends MeasureReferenceUsage> parameters, String slotName) {
		ArrayNode result = json.createArrayNode();
		for (MeasureReferenceUsage parameter : parameters) {
			if (parameter.getName() == null || parameter.getName().equals(slotName)) {
				throw new IllegalArgumentException("Set a name for %s in strategy action '%s'".formatted(slotName, action.getName()));
			}
			Optional<MeasureAttributeUsage<?, ?>> reference = parameter.getReference();
			if (reference.isEmpty()) continue;
			ObjectNode entry = attributeNode(reference.get(), "value");
			entry.put("name", parameter.getName());
			entry.put("id", chain(reference.get()));
			result.add(entry);
		}
		return result;
	}

	private String operandChain(ConditionUsage condition, Optional<? extends MeasureReferenceUsage> operand, String slotName) {
		return operand.flatMap(MeasureReferenceUsage::getReference).map(this::chain)
				.orElseThrow(() -> new IllegalArgumentException("Condition '%s' has no %s".formatted(condition.getName(), slotName)));
	}

	private String chain(MeasureAttributeUsage<?, ?> attribute) {
		AbstractType<?, ?> parent = attribute.getParent().orElseThrow();
		if (ComponentUsage.class.isInstance(parent)) {
			AbstractType<?, ?> entity = parent.getParent().orElseThrow();
			return String.join(".", id(entity), parent.getName(), attribute.getName());
		}
		return String.join(".", id(parent), parent.getName() + CONST_COMPONENT_SUFFIX, attribute.getName());
	}

	private String constComponentTypeId(EntityUsage entity) {
		return id(UUID.nameUUIDFromBytes(new TreeSet<>(schema(entity.getConstAttributes())).toString().getBytes(StandardCharsets.UTF_8)));	}

	private String constComponentId(EntityUsage entity) {
		return id(entity)+CONST_COMPONENT_SUFFIX;
	}



	private String dataType(MeasureAttributeUsage<?, ?> attribute) {
		return attribute.getDataType().flatMap(type -> type.getValue()).map(EnumAttributeDataType::getStringRepresentation).orElse("STRING");
	}

	private int retention(Optional<? extends TwinAttributeUsage<?, ?>> days) {
		return literal(days).map(value -> Number.class.cast(value).intValue()).orElse(DEFAULT_RETENTION_DAYS);
	}

	private Optional<Object> literal(Optional<? extends TwinAttributeUsage<?, ?>> attribute) {
		return attribute.flatMap(TwinAttributeUsage::getExpression).filter(LiteralUsage.class::isInstance)
				.map(LiteralUsage.class::cast).map(LiteralUsage::getValue);
	}

	private JsonNode parsePayload(StrategyActionUsage action, String raw) {
		try {
			return json.readTree(raw);
		} catch (JsonProcessingException e) {
			throw new IllegalArgumentException("customPayload of strategy action '%s' is no valid JSON: %s".formatted(action.getName(), e.getOriginalMessage()), e);
		}
	}
}
