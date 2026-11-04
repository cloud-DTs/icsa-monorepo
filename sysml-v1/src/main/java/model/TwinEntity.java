package model;

import lombok.Builder;
import lombok.Getter;
import lombok.Setter;

import java.util.ArrayList;
import java.util.List;

@Getter
@Setter
public class TwinEntity extends TwinModel {

    private String entityId;
    private String entityName;
    private TwinEntity parent;
    private List<TwinEntity> subEntities = new ArrayList<>();
    private List<TwinComponent> components = new ArrayList<>();
    private String definitionId;
    private TwinDataBase hot;
    private TwinDataBase cold;


    public void attachToParent() {
        if (parent != null && !parent.getSubEntities().contains(this)) {
            parent.getSubEntities().add(this);
        }
    }

    @Override
    public String getId() {
        return entityId;
    }

}
