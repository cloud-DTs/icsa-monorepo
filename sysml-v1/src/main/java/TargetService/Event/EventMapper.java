package TargetService.Event;

import model.*;
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;
import org.mapstruct.Named;
import org.mapstruct.factory.Mappers;

import java.util.ArrayList;
import java.util.List;

@Mapper
public interface EventMapper {

    EventMapper INSTANCE = Mappers.getMapper(EventMapper.class);

    @Mapping(target = "condition", source = ".", qualifiedByName = "toCondition")
    @Mapping(target = "action", expression = "java(toAction(event))")
    EventDTO toDTO(TwinStrategy event);

    @Mapping(source = "name", target = "functionName")
    @Mapping(target = "type", source = "strategyType")
    @Mapping(target = "pathToCode", source = "pathToCode")
    EventLambdaStrategyDTO toAction(TwinStrategy event);

    @Named("toCondition")
    default String toCondition(TwinStrategy strategy) {
        if (strategy == null) return null;
        String lhs = formatProperty(strategy.getLhs());
        String rhs = formatProperty(strategy.getRhs());
        String operator = strategy.getOperator() != null ? strategy.getOperator() : "==";

        return lhs + " " + operator + " " + rhs;
    }

    default String formatProperty(TwinProperty prop) {
        TwinComponentProperty prop2 = (TwinComponentProperty) prop;
        return prop2.getComponent().getParentEntity().getShortenUUID()
                + "." + prop2.getComponent().getComponentName()
                + "." + prop2.getName();
    }


    default List<EventDTO> toDTO(TwinEntity source) {
        List<EventDTO> dtos = new ArrayList<>();


        for (TwinEntity entity : source.getSubEntities()) {
            dtos.addAll(toDTO(entity));
        }
        for (TwinComponent component : source.getComponents()) {
            for (TwinStrategy strategy : component.getStrategies()) {

                EventDTO dto = toDTO(strategy);
                dto.getAction().setExternal(strategy.getPathToCode().isEmpty());
                if (dto != null) {
                    FeedBackDTO feedBack;
                    if(strategy.getFeedBack() instanceof  InternalFeedBackTopic feedBackTopic){
                        feedBack = new FeedBackInternalTopic();
                        ((FeedBackInternalTopic) feedBack).setIotDeviceId(feedBackTopic.getShortenTopic());
                    }
                    else if(strategy.getFeedBack() instanceof  ExternalFeedBackTopic feedBackTopic) {
                        feedBack = new FeedBackExternalTopic();
                        ((FeedBackExternalTopic) feedBack).setTopic(feedBackTopic.getTopic());

                    }
                    else {
                        dtos.add(dto);
                        continue;
                    }

                    if(strategy.getFeedBack().getPayload() instanceof CustomPayload customPayload){
                        CustomPayloadDTO customPayloadDTO = new CustomPayloadDTO();
                        customPayloadDTO.setPayload((customPayload.getPayload().toMap()));
                        feedBack.setPayload(customPayloadDTO);
                        feedBack.setType("mqtt");
                        dto.getAction().setFeedback(feedBack);
                        dtos.add(dto);
                    }
                    else if(strategy.getFeedBack().getPayload() instanceof ActionResultPayload actionResultPayload){
                        ResultPayloadDTO resultPayloadDTO = new ResultPayloadDTO();
                        resultPayloadDTO.payload = actionResultPayload.getPayload();
                        feedBack.setPayload(resultPayloadDTO);
                        feedBack.setType("mqtt");
                        dto.getAction().setFeedback(feedBack);
                        dtos.add(dto);
                    }
                }
            }
        }

        return dtos;
    }
    default List<EventDTO> toDTO(List<TwinEntity> entities) {
        List<EventDTO> dtos = new ArrayList<>();
        for (TwinEntity entity : entities) {
            dtos.addAll(toDTO(entity));
        }
        return dtos;
    }
}


