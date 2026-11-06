package org.example.Model.Attribute;

import org.example.Model.Enums.EnumAttributeDataTypeUsage;

import java.util.Optional;

public interface MeasureAttributeCoreApi<C extends MeasureAttributeCore> extends TwinAttributeCoreApi<C> {
	default Optional<EnumAttributeDataTypeUsage> getDataType() { return getCore().getDataType(); }
}
