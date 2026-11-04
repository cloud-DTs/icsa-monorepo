package model;

import lombok.Getter;
import lombok.Setter;
import org.json.JSONObject;

@Setter
@Getter
public class CustomPayload extends Payload {

    JSONObject payload;

}
