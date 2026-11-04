package model;

import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
public class TwinStrategy extends TwinModel {

    private String strategyId;
    private String name;
    private String description;
    private TwinComponent component;
    private String operator;
    private TwinProperty lhs;
    private TwinProperty rhs;
    private String strategyType;
    private String pathToCode;
    private String definitionId;
    private FeedBack feedBack;

    public void attachToParent() {
        if (component != null && !component.getStrategies().contains(this)) {
            component.getStrategies().add(this);
        }
    }

    @Override
    public String getId() {
        return strategyId;
    }

}
