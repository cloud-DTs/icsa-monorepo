package org.example;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.DoubleNode;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.fasterxml.jackson.databind.node.LongNode;
import com.fasterxml.jackson.databind.node.TextNode;

public class ConstValue {

	public JsonNode convert(String attributeName, String dataType, String raw) {
		try {
			return switch (dataType) {
				case "INTEGER" -> new LongNode(Long.parseLong(raw.trim()));
				case "DOUBLE" -> new DoubleNode(Double.parseDouble(raw.trim()));
				case "VECTOR_INTEGER", "VECTOR_DOUBLE", "VECTOR_STRING" -> vector(dataType, raw);
				default -> new TextNode(raw);
			};
		} catch (NumberFormatException e) {
			throw new IllegalArgumentException("Const attribute '%s': value '%s' is no %s".formatted(attributeName, raw, dataType), e);
		}
	}


	private ArrayNode vector(String dataType, String raw) {
		String body = raw.trim();
		boolean bracketed = (body.startsWith("[") && body.endsWith("]")) || (body.startsWith("(") && body.endsWith(")"));
		if (!bracketed) {
			throw new NumberFormatException("vector has to be written as [..] or (..)");
		}
		ArrayNode result = JsonNodeFactory.instance.arrayNode();
		body = body.substring(1, body.length() - 1).trim();
		if (body.isEmpty()) return result;
		for (String element : body.split(",")) {
			String value = element.trim();
			switch (dataType) {
				case "VECTOR_INTEGER" -> result.add(Long.parseLong(value));
				case "VECTOR_DOUBLE" -> result.add(Double.parseDouble(value));
				default -> result.add(unquote(value));
			}
		}
		return result;
	}

	private String unquote(String value) {
		boolean quoted = value.length() >= 2 && (value.startsWith("'") && value.endsWith("'") || value.startsWith("\"") && value.endsWith("\""));
		return quoted ? value.substring(1, value.length() - 1) : value;
	}
}
