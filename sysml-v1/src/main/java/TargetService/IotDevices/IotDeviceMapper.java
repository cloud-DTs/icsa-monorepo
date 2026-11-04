package TargetService.IotDevices;

import model.TwinComponent;
import model.TwinComponentProperty;
import model.TwinEntity;
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;
import org.mapstruct.factory.Mappers;

import java.util.ArrayList;
import java.util.List;

@Mapper
public interface IotDeviceMapper {
    IotDeviceMapper INSTANCE = Mappers.getMapper(IotDeviceMapper.class);

    @Mapping(source="shortenUUID", target = "id")
    @Mapping(source="properties", target = "properties")
    IotDeviceDTO toIotDeviceDTO(TwinComponent twinComponent);

    @Mapping(source = "name",target = "name")
    @Mapping(source = "dataType",target = "dataType")
    @Mapping(source = "initialValue", target = "initValue")
    IotDevicePropertyDTO toIotDevicePropertyDTO(TwinComponentProperty twinComponentProperty);


    List<IotDeviceDTO> toIotDeviceDTOs(List<TwinComponent> twinComponents);


    default List<IotDeviceDTO> toIotDeviceDTOs(TwinEntity entity) {
        List<TwinComponent> components = collectComponentsRecursive(entity);
        return toIotDeviceDTOs(components);
    }

    default List<TwinComponent> collectComponentsRecursive(TwinEntity entity) {
        List<TwinComponent> result = new ArrayList<>();

        if (entity.getComponents() != null) {
            result.addAll(entity.getComponents());
        }
        if (entity.getSubEntities() != null) {
            for (TwinEntity child : entity.getSubEntities()) {
                result.addAll(collectComponentsRecursive(child));
            }
        }

        return result;
    }


    default List<IotDeviceDTO> fromEntitiesToIotDeviceDTOs(List<TwinEntity> entities) {
        List<IotDeviceDTO> result = new ArrayList<>();
        for (TwinEntity entity : entities) {
            result.addAll(toIotDeviceDTOs(entity));
        }


        return result;
    }

}

