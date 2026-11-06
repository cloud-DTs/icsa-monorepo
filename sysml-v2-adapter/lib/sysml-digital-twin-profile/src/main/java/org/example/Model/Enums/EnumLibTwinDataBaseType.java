package org.example.Model.Enums;

import lombok.Getter;

public enum EnumLibTwinDataBaseType implements TwinEnum {

	RELATIONAL("RELATIONAL"), TIMESERIES("TIMESERIES");
	@Getter
	private final String stringRepresentation;

	EnumLibTwinDataBaseType(String stringRepresentation) {
		this.stringRepresentation = stringRepresentation;
	}
}
