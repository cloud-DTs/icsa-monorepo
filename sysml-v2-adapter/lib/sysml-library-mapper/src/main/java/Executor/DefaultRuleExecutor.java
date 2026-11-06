package Executor;


import Mapper.NewUtil;
import Rules.CheckUnMappedElements;
import Rules.MultiType;
import Rules.MultiplicityRule;

import java.util.List;

public class DefaultRuleExecutor extends Executor {


	public List<GenerelRules> getGeneralRules(NewUtil newUtil) {
		return List.of(new MultiplicityRule(newUtil),new MultiType(newUtil));
	}

	@Override
	public List<SemanticRule> getSemanticRules(NewUtil newUtil) {
		return List.of(new CheckUnMappedElements(newUtil));
	}
}
