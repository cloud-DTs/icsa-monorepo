package org.example.Model.Condition;

import Mapper.Mapper;
import Model.AbstractType;
import org.example.Model.DTCore;
import lombok.Getter;
import org.omg.sysml.lang.sysml.Feature;
import org.omg.sysml.lang.sysml.Type;
import Model.Slots;
import org.example.Model.Attribute.LeftOperandUsage;
import org.example.Model.Attribute.RightOperandUsage;
import org.example.Model.Enums.EnumComparisonOperatorUsage;
import org.example.Model.Strategy.StrategyActionUsage;

import java.util.List;
import java.util.Optional;

// slots of DigitalTwinLibrary::LibTwinConditionAction
public class ConditionCore extends DTCore {

	@Getter private Optional<LeftOperandUsage> leftOperand = Optional.empty();
	@Getter private Optional<EnumComparisonOperatorUsage> operator = Optional.empty();
	@Getter private Optional<RightOperandUsage> rightOperand = Optional.empty();
	@Getter private List<StrategyActionUsage> strategyActions = List.of();

	public ConditionCore(Type sysmlElement, Mapper mapper) {
		super(sysmlElement, mapper);
	}

	@Override
	protected void fillDTSlots(AbstractType<?, ?> owner,List<Feature> features) {
		leftOperand = Slots.atMostOne(owner, "leftOperand", slot(mapper.mapSlot("leftOperand", owner, LeftOperandUsage.class)));
		operator = Slots.atMostOne(owner, "operator", slot(mapper.mapSlot("operator", owner, EnumComparisonOperatorUsage.class)));
		rightOperand = Slots.atMostOne(owner, "rightOperand", slot(mapper.mapSlot("rightOperand", owner, RightOperandUsage.class)));
		strategyActions = slot(Slots.mapAll(mapper, owner, features, StrategyActionUsage.class));
	}

}
