package TargetService.Hierarchy;

import TargetService.DeployerModelDTO;
import model.TwinComponent;
import model.TwinEntity;
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;
import org.mapstruct.factory.Mappers;

import java.util.List;

@Mapper
public interface HierarchyMapper {

    HierarchyMapper INSTANCE = Mappers.getMapper(HierarchyMapper.class);

    @Mapping(target = "id",source = "shortenUUID")
    @Mapping(target = "name", source = "entityName")
    @Mapping(target = "type", constant = "entity")
    @Mapping(target = "components", source = "components")
    @Mapping(target = "subEntities", source = "subEntities")
    HierarchyEntityDTO toHierarchyEntityDTO(TwinEntity twin);


    @Mapping(target = "name", source = "componentName")
    @Mapping(target = "type", constant = "component")
    @Mapping(target = "iotDeviceId", source = "shortenUUID")
    HierarchyComponentDTO toHierarchyComponentDTO(TwinComponent twin);

    default List<HierarchyEntityDTO> toHierarchyEntityDTOs(List<TwinEntity> twinEntities) {
        return twinEntities.stream().map(this::toHierarchyEntityDTO).toList();
    }

    default List<HierarchyEntityDTO> toHierarchyEntityDTOs(TwinEntity entity) {
        return List.of(toHierarchyEntityDTO(entity));
    }


}
