package org.example.Model.Enums;

import lombok.Getter;

public enum EnumAttributeDataType implements TwinEnum {

	STRING("STRING"), DOUBLE("DOUBLE"), INTEGER("INTEGER"), VECTOR_DOUBLE("VECTOR_DOUBLE"), VECTOR_INTEGER("VECTOR_INTEGER"), VECTOR_STRING("VECTOR_STRING");
	@Getter
	private final String stringRepresentation;

	EnumAttributeDataType(String stringRepresentation) {
		this.stringRepresentation = stringRepresentation;
	}
}
