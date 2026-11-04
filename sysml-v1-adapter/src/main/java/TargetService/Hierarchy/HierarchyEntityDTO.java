package TargetService.Hierarchy;

import TargetService.IotDevices.IotDeviceConstPropertyDTO;
import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonUnwrapped;
import com.fasterxml.jackson.annotation.JsonValue;
import lombok.Getter;
import lombok.Setter;

import java.util.ArrayList;
import java.util.List;

@Getter
@Setter
public class HierarchyEntityDTO extends HierarchyChildrenDTO {

    @JsonIgnore
    private List<HierarchyEntityDTO> subEntities;
    @JsonIgnore
    private List<HierarchyComponentDTO> components;

    private String id;
    @JsonIgnore
    private List<IotDeviceConstPropertyDTO> constProperties = new ArrayList<>();


    @JsonProperty("children")
    public List<HierarchyChildrenDTO> getChildren() {
        List<HierarchyChildrenDTO> entityDTOS = new ArrayList<>();
        entityDTOS.addAll(this.subEntities);
        entityDTOS.addAll(this.components);
        return entityDTOS;
    }

}
