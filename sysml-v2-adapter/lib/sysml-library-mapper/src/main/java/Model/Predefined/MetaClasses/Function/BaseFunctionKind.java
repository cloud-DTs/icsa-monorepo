package Model.Predefined.MetaClasses.Function;

public enum BaseFunctionKind implements FunctionKind {

	ADD("+"), SUBTRACT("-"), MULTIPLY("*"), DIVIDE("/"), POWER("**"), CARET("^"), MODULO("%"), CHAIN("."), COLLECTION(","),

	LESS_THAN("<"), GREATER_THAN(">"), LESS_EQUAL("<="), GREATER_EQUAL(">="), EQUAL("=="),

	AND("&"), OR("|"), NOT("not"),

	ABS("abs"), MAX("max"), MIN("min"), SQRT("sqrt"), FLOOR("floor"), ROUND("round"),

	LENGTH("Length"), SUBSTRING("Substring"),

	TO_STRING("ToString"), TO_INTEGER("ToInteger"), TO_REAL("ToReal"), TO_BOOLEAN("ToBoolean"), TO_NATURAL("ToNatural"), TO_RATIONAL("ToRational"),

	SUM("sum"), PRODUCT("product"),

	SIZE("size"), IS_EMPTY("isEmpty"), INDEX("#"), INCLUDING("including"), EXCLUDING("excluding"), INCLUDING_AT("includingAt"), EXCLUDING_AT("excludingAt");

	private final String symbol;

	BaseFunctionKind(String symbol) {
		this.symbol = symbol;
	}

	public static BaseFunctionKind fromSymbol(String symbol) {
		for (BaseFunctionKind kind : values()) {
			if (kind.symbol.equals(symbol)) {
				return kind;
			}
		}
		throw new IllegalArgumentException("Unknown base function: " + symbol + "We allow the following base functions: " + String.join(", ", java.util.Arrays.stream(values()).map(BaseFunctionKind::getSymbol).toArray(String[]::new)));
	}

	public String getSymbol() {
		return symbol;
	}

	@Override
	public String getSysmbol() {
		return symbol;
	}
}