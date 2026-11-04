package TargetService.Event;

import com.fasterxml.jackson.annotation.JsonUnwrapped;
import lombok.Getter;
import lombok.Setter;
import org.json.JSONObject;

import java.util.Map;

@Getter
@Setter
public class CustomPayloadDTO extends PayloadDTO {

    Map<String, Object> payload;
}
