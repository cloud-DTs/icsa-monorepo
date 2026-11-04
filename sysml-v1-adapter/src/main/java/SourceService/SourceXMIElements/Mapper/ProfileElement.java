package SourceService.SourceXMIElements.Mapper;

import SourceService.SourceXMIElements.AbstractXMIComponent;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
@AllArgsConstructor
public class ProfileElement {
    private AbstractXMIComponent abstractXMIComponent;
    private Stereotypes stereotype;
}
