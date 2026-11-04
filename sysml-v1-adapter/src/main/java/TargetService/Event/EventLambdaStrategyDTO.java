package TargetService.Event;

import com.fasterxml.jackson.annotation.JsonInclude;
import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
public class EventLambdaStrategyDTO extends EventStrategyDTO {

    private String type;
    private String functionName;
    private Boolean external;
    private String pathToCode;
    @JsonInclude(JsonInclude.Include.NON_NULL)
    private FeedBackDTO feedback;
}
