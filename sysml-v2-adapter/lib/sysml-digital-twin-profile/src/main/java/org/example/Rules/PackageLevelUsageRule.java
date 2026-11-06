package org.example.Rules;
import Executor.GenerelRules;
import Mapper.NewUtil;
import org.omg.sysml.lang.sysml.Usage;

public class PackageLevelUsageRule extends GenerelRules {

	public PackageLevelUsageRule(NewUtil utils) {
		super(utils);
	}

	@Override
	public boolean isValid() throws IllegalArgumentException {
		for (Usage usage : utilsManager.collect(Usage.class)) {
			if (org.omg.sysml.lang.sysml.Package.class.isInstance(usage.getOwner())) {
				throw new IllegalArgumentException("'%s' is a usage directly in package '%s'; only definitions are allowed there"
						.formatted(usage.getName(), usage.getOwner().getName()));
			}
		}
		return true;
	}
}
