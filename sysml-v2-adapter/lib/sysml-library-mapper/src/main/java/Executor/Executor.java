package Executor;


import Main.ResultConverter;
import Mapper.NewUtil;

import java.util.List;

public abstract class Executor {

	public abstract List<GenerelRules> getGeneralRules(NewUtil newUtil);
	public abstract List<SemanticRule> getSemanticRules(NewUtil newUtil);

	public void executeGeneralRules(NewUtil newUtil) {
		for (GenerelRules rule : getGeneralRules(newUtil)) rule.isValid();
	}

	public void executeSemanticRules(NewUtil newUtil, ResultConverter resultConverter) throws SemanticException {
		for (SemanticRule rule : getSemanticRules(newUtil)) rule.isValid(resultConverter);
	}
}