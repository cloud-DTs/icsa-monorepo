package org.example.Model.Strategy;

import Mapper.Mapper;
import Model.AbstractType;
import java.nio.file.Files;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;
import org.example.Model.DTCore;
import lombok.Getter;
import org.example.Model.Expression.TwinLiteralStringUsage;

import org.omg.sysml.lang.sysml.Feature;
import org.omg.sysml.lang.sysml.Type;
import Model.Slots;
import org.example.Model.Attribute.InputParameterUsage;
import org.example.Model.Attribute.OutputParameterUsage;
import org.example.Model.Attribute.TwinAttributeBooleanUsage;
import org.example.Model.Attribute.TwinAttributeStringUsage;
import org.example.Model.Component.ComponentTopicUsage;
import org.example.Model.Enums.EnumFeedbackTopicTypeUsage;
import org.example.Model.Enums.EnumStrategyTypeUsage;

import java.util.List;
import java.util.Optional;

// slots of DigitalTwinLibrary::LibTwinStrategyAction
public class StrategyActionCore extends DTCore {

	@Getter private TwinAttributeStringUsage actionName;
	@Getter private Optional<TwinAttributeStringUsage> description = Optional.empty();
	@Getter private TwinAttributeBooleanUsage external;
	@Getter private TwinAttributeStringUsage pathToCode;
	@Getter private List<InputParameterUsage> inputParameters = List.of();
	@Getter private List<OutputParameterUsage> outputParameters = List.of();
	@Getter private EnumStrategyTypeUsage strategyType;
	@Getter private Optional<TwinAttributeStringUsage> customPayload = Optional.empty();
	@Getter private Optional<EnumFeedbackTopicTypeUsage> feedbackTopicType = Optional.empty();
	@Getter private Optional<ComponentTopicUsage> componentTopic = Optional.empty();
	@Getter private Optional<TwinAttributeStringUsage> externalTopic = Optional.empty();

	public StrategyActionCore(Type sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	@Override
	protected void fillDTSlots(AbstractType<?, ?> owner,List<Feature> features) {
		actionName = Slots.exactlyOne(owner, "name", slot(mapper.mapSlot("name", owner, TwinAttributeStringUsage.class)));
		description = Slots.atMostOne(owner, "description", slot(mapper.mapSlot("description", owner, TwinAttributeStringUsage.class)));
		external = Slots.exactlyOne(owner, "external", slot(mapper.mapSlot("external", owner, TwinAttributeBooleanUsage.class)));
		pathToCode = Slots.exactlyOne(owner, "pathToCode", slot(mapper.mapSlot("pathToCode", owner, TwinAttributeStringUsage.class)));
		testPath(pathToCode);
		inputParameters = slot(mapper.mapSlot("inputParameters", owner, InputParameterUsage.class));
		outputParameters = slot(mapper.mapSlot("outputParameters", owner, OutputParameterUsage.class));
		strategyType = Slots.exactlyOne(owner, "strategyType", slot(mapper.mapSlot("strategyType", owner, EnumStrategyTypeUsage.class)));
		customPayload = Slots.atMostOne(owner, "customPayload", slot(mapper.mapSlot("customPayload", owner, TwinAttributeStringUsage.class)));
		feedbackTopicType = Slots.atMostOne(owner, "feedbackTopicType", slot(mapper.mapSlot("feedbackTopicType", owner, EnumFeedbackTopicTypeUsage.class)));
		componentTopic = Slots.atMostOne(owner, "componentTopic", slot(mapper.mapSlot("componentTopic", owner, ComponentTopicUsage.class)));
		externalTopic = Slots.atMostOne(owner, "externalTopic", slot(mapper.mapSlot("externalTopic", owner, TwinAttributeStringUsage.class)));
	}

	private void testPath(TwinAttributeStringUsage pathToCode) {
		pathToCode.getExpression().filter(TwinLiteralStringUsage.class::isInstance).map(TwinLiteralStringUsage.class::cast)
				.map(TwinLiteralStringUsage::getValue)
				.filter(path -> !exists(path))
				.ifPresent(path -> System.out.println("Warning: The path to code '" + path + "' does not exist for " + this.sysmlElement.path() + " or is no zip file. Please check the path."));
	}
	private boolean exists(String path) {
		try {

			var file = Path.of(path);
			return Files.exists(file) && file.getFileName().toString().endsWith(".zip");

		} catch (InvalidPathException e) {
			return false;
		}
	}
}
