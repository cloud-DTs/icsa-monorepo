package TargetService;

import TargetService.Event.EventMapper;
import TargetService.Hierarchy.HierarchyMapper;
import TargetService.IotDevices.IotDeviceMapper;
import model.TwinEntity;
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;
import org.mapstruct.factory.Mappers;

import java.util.List;

@Mapper(uses = {HierarchyMapper.class, IotDeviceMapper.class, EventMapper.class})
public interface DeployerMapper {
    DeployerMapper INSTANCE = Mappers.getMapper(DeployerMapper.class);

    @Mapping(source=".",target = "configIotDevice")
    @Mapping(source = ".",target = "configHierarchy")
    @Mapping(source = ".",target = "configEvent")
    DeployerModelDTO  toDeployerModelDTO(TwinEntity entity);

    @Mapping(source="twin",target = "configIotDevice")
    @Mapping(source = "twin",target = "configHierarchy")
    @Mapping(source = "twin",target = "configEvent")
    DeployerModelDTO  toDeployerModelDTO(Integer dummy,List<TwinEntity> twin);

    default DeployerModelDTO toDeployerModelDTO(List<TwinEntity> twin){
        return toDeployerModelDTO(0,twin);
    }

}
