package model;

import com.luigivismara.shortuuid.ShortUuid;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import registry.TwinRegistry;

import java.util.UUID;

@Getter
public abstract class TwinModel extends TwinIdentity {

    public abstract void attachToParent();

}
