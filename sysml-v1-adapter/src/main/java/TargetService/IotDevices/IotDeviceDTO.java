package TargetService.IotDevices;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Getter;
import lombok.Setter;

import java.util.ArrayList;
import java.util.List;



@Getter
@Setter
public class IotDeviceDTO {

    private String id;
    private List<IotDevicePropertyDTO> properties = new ArrayList<>();
    @JsonIgnore
    private List<IotDeviceConstPropertyDTO> constProperties = new ArrayList<>();
}
