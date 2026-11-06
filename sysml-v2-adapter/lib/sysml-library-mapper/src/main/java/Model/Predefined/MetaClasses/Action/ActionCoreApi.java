package Model.Predefined.MetaClasses.Action;

import Model.Core.CoreApi;
import Model.Usage;

import java.util.List;

public interface ActionCoreApi<C extends ActionCore> extends CoreApi<C> {

	default List<? extends Usage<?, ?,?>> getInputs() { return getCore().getInputs(); }
	default List<? extends Usage<?, ?,?>> getOutputs() { return getCore().getOutputs(); }
	default List<? extends ActionMapUsage<?, ?, ?>> getActions() { return getCore().getActions(); }
	default List<? extends SuccessionMapUsage> getSuccessions() { return getCore().getSuccessions(); }
}
