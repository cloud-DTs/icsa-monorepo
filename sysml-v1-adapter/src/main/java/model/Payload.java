package model;

import lombok.Getter;
import lombok.Setter;

@Setter
@Getter
public abstract class Payload {

    public abstract  <T> T getPayload();
}
