package org.example.Model.Entity;

import Model.Core.CoreApi;
import org.example.Model.Attribute.ConstAttributeUsage;
import org.example.Model.Component.ComponentUsage;
import org.example.Model.Condition.ConditionUsage;

import java.util.List;

public interface EntityCoreApi extends CoreApi<EntityCore> {
	default List<ConstAttributeUsage> getConstAttributes() { return getCore().getConstAttributes(); }
	default List<EntityUsage> getEntities() { return getCore().getEntities(); }
	default List<ComponentUsage> getComponents() { return getCore().getComponents(); }
	default List<ConditionUsage> getStrategies() { return getCore().getStrategies(); }
}
