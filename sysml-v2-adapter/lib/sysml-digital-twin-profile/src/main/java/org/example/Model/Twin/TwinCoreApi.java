package org.example.Model.Twin;

import Model.Core.CoreApi;
import org.example.Model.Attribute.TwinAttributeIntegerUsage;
import org.example.Model.Entity.EntityUsage;
import org.example.Model.Condition.ConditionUsage;
import org.example.Model.Enums.EnumLibTwinDataBaseTypeUsage;

import java.util.List;
import java.util.Optional;

public interface TwinCoreApi extends CoreApi<TwinCore> {
	default List<ConditionUsage> getConditions() { return getCore().getConditions(); }
	default List<EntityUsage> getEntities() { return getCore().getEntities(); }
	default Optional<EnumLibTwinDataBaseTypeUsage> getHotDatabaseType() { return getCore().getHotDatabaseType(); }
	default Optional<TwinAttributeIntegerUsage> getHotDatabaseRetentionDays() { return getCore().getHotDatabaseRetentionDays(); }
	default Optional<EnumLibTwinDataBaseTypeUsage> getColdDataBaseType() { return getCore().getColdDataBaseType(); }
	default Optional<TwinAttributeIntegerUsage> getColdDatabaseRetentionDays() { return getCore().getColdDatabaseRetentionDays(); }
}
