package org.example.Model.Component;

import Model.Core.CoreApi;
import org.example.Model.Attribute.MeasureAttributeUsage;

import java.util.List;

public interface ComponentCoreApi extends CoreApi<ComponentCore> {
	default List<MeasureAttributeUsage<?, ?>> getMeasurements() { return getCore().getMeasurements(); }
}
