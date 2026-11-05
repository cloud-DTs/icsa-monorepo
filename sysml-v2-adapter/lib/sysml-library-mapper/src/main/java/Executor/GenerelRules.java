package Executor;


import Mapper.NewUtil;

public abstract class GenerelRules {

	protected final NewUtil utilsManager;

	public GenerelRules(NewUtil utils) {
		this.utilsManager = utils;
	}

	public abstract boolean isValid() throws IllegalArgumentException;


}
