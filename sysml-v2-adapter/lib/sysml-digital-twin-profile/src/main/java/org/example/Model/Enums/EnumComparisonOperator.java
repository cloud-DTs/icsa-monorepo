package org.example.Model.Enums;

import lombok.Getter;

public enum EnumComparisonOperator implements TwinEnum {

	GREATER_THAN("GREATER_THAN"), LESS_THAN("LESS_THAN"), EQUAL("EQUAL"), GREATER_EQUAL("GREATER_EQUAL"), LESS_EQUAL("LESS_EQUAL"), NOT_EQUAL("NOT_EQUAL");
	@Getter
	private final String stringRepresentation;

	EnumComparisonOperator(String stringRepresentation) {
		this.stringRepresentation = stringRepresentation;
	}
}
