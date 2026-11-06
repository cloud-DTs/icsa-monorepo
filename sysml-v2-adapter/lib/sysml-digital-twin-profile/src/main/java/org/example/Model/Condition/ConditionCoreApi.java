package org.example.Model.Condition;

import Model.Core.CoreApi;
import org.example.Model.Attribute.LeftOperandUsage;
import org.example.Model.Attribute.RightOperandUsage;
import org.example.Model.Enums.EnumComparisonOperatorUsage;
import org.example.Model.Strategy.StrategyActionUsage;

import java.util.List;
import java.util.Optional;

public interface ConditionCoreApi extends CoreApi<ConditionCore> {
	default Optional<LeftOperandUsage> getLeftOperand() { return getCore().getLeftOperand(); }
	default Optional<EnumComparisonOperatorUsage> getOperator() { return getCore().getOperator(); }
	default Optional<RightOperandUsage> getRightOperand() { return getCore().getRightOperand(); }
	default List<StrategyActionUsage> getStrategyActions() { return getCore().getStrategyActions(); }
}
