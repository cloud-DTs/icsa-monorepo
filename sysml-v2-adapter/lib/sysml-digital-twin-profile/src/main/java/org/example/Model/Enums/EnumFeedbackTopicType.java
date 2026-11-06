package org.example.Model.Enums;

import lombok.Getter;

public enum EnumFeedbackTopicType implements TwinEnum {

	EXTERN("EXTERN"), INTERN("INTERN"), NOFEEDBACK("NOFEEDBACK");
	@Getter
	private final String stringRepresentation;

	EnumFeedbackTopicType(String stringRepresentation) {
		this.stringRepresentation = stringRepresentation;
	}
}
