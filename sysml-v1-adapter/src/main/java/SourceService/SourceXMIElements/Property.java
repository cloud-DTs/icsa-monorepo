package SourceService.SourceXMIElements;

import lombok.*;
import org.w3c.dom.Element;

@Getter
@Setter
@NoArgsConstructor
@ToString(callSuper = true)
public class Property {
    private String stereoType;

    public static Property parse(Element prop) {
        Property property = new Property();
        if(prop == null){
            property.setStereoType(null);
            return property;
        }

        property.stereoType = prop.getAttribute("stereotype");
        return property;
    }
}
