package SourceService.SourceXMIElements.Attribute;

import SourceService.SourceXMIElements.Mapper.Stereotypes;
import SourceService.SourceXMIElements.StereotypeElement;
import SourceService.SourceXMIElements.Tag;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import lombok.ToString;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

import java.util.ArrayList;
import java.util.List;

@Getter
@Setter
@NoArgsConstructor
@ToString(callSuper = true)
public class Attribute implements StereotypeElement{
    private String idref;
    private String name;
    private Initial inital_body;
    private Stereotype stereotype;
    private List<Tag> tags;
    private String eaGuid;
    private String owner;

    public static Attribute parse(Element element) {
        Attribute attribute = new Attribute();
        attribute.idref = element.getAttribute("xmi:idref");
        attribute.name = element.getAttribute("name");
        attribute.inital_body = Initial.parse((Element) element.getElementsByTagName("initial").item(0));
        attribute.tags = Tag.parse(element.getElementsByTagName("tag"));
        attribute.stereotype = Stereotype.parse((Element) element.getElementsByTagName("stereotype").item(0));
        Element model = (Element) element.getElementsByTagName("model").item(0);
        if (model != null){
            attribute.eaGuid = model.getAttribute("ea_guid");
        }
        return attribute;
    }

    public static List<Attribute> parse(NodeList elements){

        List<Attribute> attributes = new ArrayList<>();

        for (int i = 0; i < elements.getLength(); i++) {
            attributes.add(parse((Element) elements.item(i)));
        }
        return attributes;

    }

    @Override
    public Stereotypes getStereotypeName() {
        return Stereotypes.typeByName(stereotype.getStereotype());
    }
}
