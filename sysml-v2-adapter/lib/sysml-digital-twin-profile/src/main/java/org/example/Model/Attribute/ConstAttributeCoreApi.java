package org.example.Model.Attribute;

import java.util.Optional;

public interface ConstAttributeCoreApi extends MeasureAttributeCoreApi<ConstAttributeCore> {
	default Optional<TwinAttributeStringUsage> getValue() { return getCore().getValue(); }
}
