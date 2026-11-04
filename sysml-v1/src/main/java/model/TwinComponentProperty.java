package model;

import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
public class TwinComponentProperty extends TwinProperty{
    private String propertyGuid;
    private String name;
    private String dataType;
    private String initialValue;
    private TwinComponent component;


    @Override
    public String getId() {
        return component.getId()+name;
    }

    @Override
    public void attachToParent() {
        this.component.getProperties().add(this);
    }

}
