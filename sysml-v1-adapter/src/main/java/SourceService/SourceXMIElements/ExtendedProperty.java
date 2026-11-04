package SourceService.SourceXMIElements;

import lombok.Builder;
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

@Getter
@Setter
@Builder
@ToString(callSuper = true)
public class ExtendedProperty {
    private String runState;
}


