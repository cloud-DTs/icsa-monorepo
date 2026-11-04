package TargetService;

import TargetService.Event.EventDTO;
import TargetService.Hierarchy.HierarchyEntityDTO;
import TargetService.IotDevices.IotDeviceDTO;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Getter;
import lombok.Setter;

import java.util.List;

@Getter
@Setter
public class DeployerModelDTO {
    @JsonProperty("config_hierarchy")
    private List<HierarchyEntityDTO> configHierarchy;
    @JsonProperty("config_iot_device")
    private List<IotDeviceDTO> configIotDevice;
    @JsonProperty("config_event")
    private List<EventDTO> configEvent;
}
