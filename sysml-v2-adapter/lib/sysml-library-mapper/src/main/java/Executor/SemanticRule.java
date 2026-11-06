package Executor;


import Main.ResultConverter;
import Mapper.NewUtil;

public abstract class SemanticRule {


	protected NewUtil newUtil;

	public SemanticRule(NewUtil newUtil){
		this.newUtil = newUtil;
	}
	public abstract boolean isValid(ResultConverter resultConverter) throws SemanticException;


}
