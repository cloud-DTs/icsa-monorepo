package TargetService.IotDevices;

import com.fasterxml.jackson.annotation.JsonInclude;
import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
public class IotDevicePropertyDTO {

    private String name;
    private String dataType;
    @JsonInclude(JsonInclude.Include.NON_NULL)
    private Object initValue;

    public void setInitValue(String rawValue) {
        if (rawValue == null) {
            this.initValue = null;
            return;
        }
        switch (dataType.toUpperCase()) {
            case "DOUBLE":
                this.initValue = Double.valueOf(rawValue);
                break;

            case "INTEGER":
                this.initValue = Integer.valueOf(rawValue);
                break;
            default:
                this.initValue = rawValue;
                break;
        }
    }
}
