package org.example;

import java.math.BigInteger;
import java.nio.ByteBuffer;
import java.util.UUID;

public class ShortUuid {

	private static final String ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
	private static final int LENGTH = 22;
	private static final BigInteger BASE = BigInteger.valueOf(ALPHABET.length());

	public String encode(UUID uuid) {
		ByteBuffer bytes = ByteBuffer.allocate(16);
		bytes.putLong(uuid.getMostSignificantBits());
		bytes.putLong(uuid.getLeastSignificantBits());
		BigInteger number = new BigInteger(1, bytes.array());

		StringBuilder reversed = new StringBuilder();
		while (number.signum() > 0) {
			BigInteger[] division = number.divideAndRemainder(BASE);
			reversed.append(ALPHABET.charAt(division[1].intValue()));
			number = division[0];
		}
		while (reversed.length() < LENGTH) {
			reversed.append(ALPHABET.charAt(0));
		}
		return reversed.reverse().toString();
	}
}
