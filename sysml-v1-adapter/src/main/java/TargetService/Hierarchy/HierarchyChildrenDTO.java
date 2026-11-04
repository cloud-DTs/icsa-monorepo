package TargetService.Hierarchy;

import com.fasterxml.jackson.annotation.JsonSubTypes;
import lombok.Getter;
import lombok.Setter;

import java.util.List;

@JsonSubTypes({
        @JsonSubTypes.Type(value = HierarchyEntityDTO.class),
        @JsonSubTypes.Type(value = HierarchyComponentDTO.class)
})
@Setter
@Getter
public class HierarchyChildrenDTO {
    private String name;
    private String type;
    private String definitionId;
}
