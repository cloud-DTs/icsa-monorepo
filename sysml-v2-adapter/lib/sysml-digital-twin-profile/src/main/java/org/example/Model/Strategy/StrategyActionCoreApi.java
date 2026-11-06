package org.example.Model.Strategy;

import Model.Core.CoreApi;
import org.example.Model.Attribute.InputParameterUsage;
import org.example.Model.Attribute.OutputParameterUsage;
import org.example.Model.Attribute.TwinAttributeBooleanUsage;
import org.example.Model.Attribute.TwinAttributeStringUsage;
import org.example.Model.Component.ComponentTopicUsage;
import org.example.Model.Enums.EnumFeedbackTopicTypeUsage;
import org.example.Model.Enums.EnumStrategyTypeUsage;

import java.util.List;
import java.util.Optional;

public interface StrategyActionCoreApi extends CoreApi<StrategyActionCore> {
	default TwinAttributeStringUsage getActionName() { return getCore().getActionName(); }
	default Optional<TwinAttributeStringUsage> getDescription() { return getCore().getDescription(); }
	default TwinAttributeBooleanUsage getExternal() { return getCore().getExternal(); }
	default TwinAttributeStringUsage getPathToCode() { return getCore().getPathToCode(); }
	default List<InputParameterUsage> getInputParameters() { return getCore().getInputParameters(); }
	default List<OutputParameterUsage> getOutputParameters() { return getCore().getOutputParameters(); }
	default EnumStrategyTypeUsage getStrategyType() { return getCore().getStrategyType(); }
	default Optional<TwinAttributeStringUsage> getCustomPayload() { return getCore().getCustomPayload(); }
	default Optional<EnumFeedbackTopicTypeUsage> getFeedbackTopicType() { return getCore().getFeedbackTopicType(); }
	default Optional<ComponentTopicUsage> getComponentTopic() { return getCore().getComponentTopic(); }
	default Optional<TwinAttributeStringUsage> getExternalTopic() { return getCore().getExternalTopic(); }
}
