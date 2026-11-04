package SourceService.SourceXMIElements.Element;

import SourceService.SourceXMIElements.AbstractXMIComponent;
import SourceService.SourceXMIElements.Attribute.Attribute;
import SourceService.SourceXMIElements.ExtendedProperty;
import SourceService.SourceXMIElements.Mapper.Stereotypes;
import SourceService.SourceXMIElements.Property;
import SourceService.SourceXMIElements.Tag;
import lombok.*;
import org.w3c.dom.Element;


import java.util.List;


@Getter
@Setter
@ToString(callSuper = true)
@NoArgsConstructor
public class EAElement extends AbstractXMIComponent {

    private String idref;
    private String type;
    private String name;
    private List<Attribute> attributes;
    private List<Link> links;
    private String owner;
    private String eaGuid;
    private String extendedRunState;

    public static EAElement parse(Element element) {
        EAElement eaElement = new EAElement();
        eaElement.idref = element.getAttribute("xmi:idref");
        eaElement.type = element.getAttribute("xmi:type");
        eaElement.name = element.getAttribute("name");
        eaElement.parseProperty(element.getElementsByTagName("properties"));
        eaElement.setTags(Tag.parse(element.getElementsByTagName("tag")));
        eaElement.attributes = Attribute.parse(element.getElementsByTagName("attribute"));
        Element link = (Element) element.getElementsByTagName("links").item(0);
        if (link != null){
            eaElement.links = Link.parse(link.getElementsByTagName("Connector"));
        }
        Element model = (Element) element.getElementsByTagName("model").item(0);
        if (model != null){
            eaElement.owner = model.getAttribute("owner");
            eaElement.eaGuid = model.getAttribute("ea_guid");
        }
        Element extendedProperties = (Element) element.getElementsByTagName("extendedProperties").item(0);
        if (extendedProperties != null) {
            eaElement.extendedRunState = extendedProperties.getAttribute("runstate");
        }
        return eaElement;
    }

}


