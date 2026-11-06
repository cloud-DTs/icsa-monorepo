package Rules;


import Executor.SemanticException;
import Executor.SemanticRule;
import Main.ResultConverter;
import Mapper.NewUtil;
import Model.AbstractType;
import Model.Definition;
import Model.Predefined.MetaClasses.Expression.ReferenceUsage;
import Model.Usage;
import org.omg.sysml.lang.sysml.*;

import java.util.Set;
import java.util.stream.Collectors;

public class CheckUnMappedElements extends SemanticRule {
	public CheckUnMappedElements(NewUtil newUtil) {
		super(newUtil);
	}

	@Override
	public boolean isValid(ResultConverter resultConverter) throws SemanticException {
		Set<Element> mapped = resultConverter.getAll().stream().map(AbstractType::getSysmlElement).collect(Collectors.toSet());

		for (Element type : newUtil.getResourceContainer().getUserResources().getAllElements()) {
			if (isModeledByUser(type) && !mapped.contains(type)) {
				throw new SemanticException("Element " + type.getName() + " with path " + type.path() + " is not mapped in the database. It is placed wrong");
			}
		}
		return true;
	}


	private boolean isModeledByUser(Element type) {
		if (!(type instanceof Usage || type instanceof Definition)) return false;
		if (type instanceof Expression || type instanceof ReferenceUsage) return false;
		if (type instanceof ConjugatedPortDefinition) return false;
		if (type instanceof SuccessionAsUsage && type.getOwner() instanceof TransitionUsage) return false;
		Membership membership = type.getOwningMembership();
		if (membership != null && membership.isImplied()) return false;
		for (Element owner = type.getOwner(); owner != null; owner = owner.getOwner()) {
			if (owner instanceof Expression) return false;
		}
		return true;
	}
}
