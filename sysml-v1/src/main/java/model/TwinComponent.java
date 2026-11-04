package model;

import lombok.Builder;
import lombok.Getter;
import lombok.Setter;

import java.util.ArrayList;
import java.util.List;

@Getter
@Setter
public class TwinComponent extends TwinModel {

    private String componentId;
    private String componentName;
    private String componentType;
    private TwinEntity parentEntity;
    private List<TwinComponentProperty> properties = new ArrayList<>();
    private List<TwinStrategy> strategies = new ArrayList<>();
    private String deviceId;
    private String definitionId;

    public void attachToParent() {
        if (parentEntity != null && !parentEntity.getComponents().contains(this)) {
            parentEntity.getComponents().add(this);
        }

    }

    @Override
    public String getId() {
        return componentId;
    }
}
