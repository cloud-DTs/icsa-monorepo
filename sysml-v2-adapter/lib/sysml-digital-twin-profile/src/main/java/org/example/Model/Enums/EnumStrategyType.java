package org.example.Model.Enums;

import lombok.Getter;

public enum EnumStrategyType implements TwinEnum {

	LAMBDA("LAMBDA");
	@Getter
	private final String stringRepresentation;

	EnumStrategyType(String stringRepresentation) {
		this.stringRepresentation = stringRepresentation;
	}
}
