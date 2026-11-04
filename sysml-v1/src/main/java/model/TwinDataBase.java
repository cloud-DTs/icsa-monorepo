package model;

import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
public class TwinDataBase extends TwinIdentity{
    private String dataBaseId;
    private String retentionDays;
    private String definitionId;


    @Override
    public String getId() {
        return getShortenUUID(dataBaseId);
    }
}
