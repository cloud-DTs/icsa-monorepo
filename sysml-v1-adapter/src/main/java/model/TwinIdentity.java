package model;

import com.luigivismara.shortuuid.ShortUuid;
import lombok.EqualsAndHashCode;

import java.util.UUID;

public abstract class TwinIdentity {
    @EqualsAndHashCode.Include
    public abstract String getId();

    public static String getShortenUUID(String id) {
        String[] splittedResult = id.split("EAID_");

        String prefix = "";
        String uuidStr;

        if(splittedResult.length == 2){
            prefix = splittedResult[0];
            uuidStr = splittedResult[1];
        } else {
            uuidStr = splittedResult[0];
        }

        UUID originalUuid = UUID.fromString(uuidStr.replace("_","-"));

        String shortId = ShortUuid.encode(originalUuid).toString();


        UUID decodedUuid = ShortUuid.decode(shortId);

        if(!originalUuid.equals(decodedUuid)){
            throw new IllegalStateException("Shorten UUID failed");
        }

        return prefix + "EAID-" + shortId;
    }

    public String getShortenUUID() {

        return getShortenUUID(getId());
    }
}
