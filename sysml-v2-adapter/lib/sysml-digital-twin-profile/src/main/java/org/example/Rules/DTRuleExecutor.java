package org.example.Rules;

import Executor.Executor;
import Executor.GenerelRules;
import Executor.SemanticRule;
import Mapper.NewUtil;
import Rules.MultiType;

import java.util.List;

public class DTRuleExecutor extends Executor {

	@Override
	public List<GenerelRules> getGeneralRules(NewUtil newUtil) {
		return List.of(new MultiType(newUtil),new PackageLevelUsageRule(newUtil));
	}

	@Override
	public List<SemanticRule> getSemanticRules(NewUtil newUtil) {
		return List.of();
	}
}
