package TargetService.IotDevices;

import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
public class IotDeviceConstPropertyDTO{
    public String name;
    public String dataType;
    private String value;
}
