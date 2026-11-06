package Rules;



import Executor.GenerelRules;
import Mapper.NewUtil;
import org.omg.sysml.lang.sysml.Definition;
import org.omg.sysml.lang.sysml.Feature;
import org.omg.sysml.lang.sysml.Type;
import org.omg.sysml.lang.sysml.Usage;
import org.omg.sysml.util.TypeUtil;

import java.util.HashSet;
import java.util.Set;

public class MultiType extends GenerelRules {
	public MultiType(NewUtil utils) {
		super(utils);
	}

	@Override
	public boolean isValid() throws IllegalArgumentException {
		Set<Feature> userTypes = utilsManager.collect(Feature.class);

		for (Feature userType : userTypes) {
			if (!(userType instanceof Usage || userType instanceof Definition)) {
				continue;
			}
			validateTypes(userType);
		}
		return true;
	}

	private void validateTypes(Feature element) throws IllegalArgumentException {
		Set<Type> effectiveTypes = new HashSet<>(element.getType());
		for (Type a : effectiveTypes) {
			for (Type b : effectiveTypes) {
				if (a == b) {
					continue;
				}

				boolean related = TypeUtil.isCompatible(a, b) || TypeUtil.isCompatible(b, a);

				if (a.getName().equals("Flow") || b.getName().equals("Flow")) {
					continue;
				}
				if (!related) {
					throw new IllegalArgumentException(("Type '%s' has incompatible typings '%s' and '%s'.").formatted(element.getQualifiedName(), a.getName(), b.getName()));
				}
			}
		}
	}
}
