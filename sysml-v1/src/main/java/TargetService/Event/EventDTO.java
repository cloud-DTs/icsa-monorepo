package TargetService.Event;

import lombok.Getter;
import lombok.Setter;

import java.util.ArrayList;
import java.util.List;

@Getter
@Setter
public class EventDTO {
    private String condition;
    private EventLambdaStrategyDTO action;
}
