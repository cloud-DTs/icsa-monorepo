package SourceService.SourceXMIElements.OwningAttribute;

import lombok.Getter;
import lombok.Setter;
import org.w3c.dom.Element;

@Getter
@Setter
public class OwningAttribute {
    private String id;
    private String typeId;

    public static OwningAttribute parse(Element element) {
        OwningAttribute owningAttribute = new OwningAttribute();
        owningAttribute.id = element.getAttribute("xmi:id");
        Element type = (Element) element.getElementsByTagName("type").item(0);
        if (type != null){
            owningAttribute.typeId = type.getAttribute("xmi:idref");
        }

        return owningAttribute;
    }
}
