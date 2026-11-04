package TargetService.Event;

import com.fasterxml.jackson.annotation.JsonUnwrapped;
import lombok.Getter;
import lombok.Setter;

@Setter
@Getter
public class FeedBackDTO {
    @JsonUnwrapped
    private PayloadDTO payload;
    private String type;
}
