package Model;

public class ElemWithMult {
	private final int lowerBound;
	private final int upperBound; // -1 = *

	public ElemWithMult(int lowerBound, int upperBound) {
		this.lowerBound = lowerBound;
		this.upperBound = upperBound;
	}

	public int getLowerBound() {
		return lowerBound;
	}

	public int getUpperBound() {
		return upperBound;
	}

	@Override
	public String toString() {
		return "[" + lowerBound + " .. " + upperBound + "]";
	}
}
