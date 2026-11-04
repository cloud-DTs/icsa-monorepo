package SourceService.SourceXMIElements;

import SourceService.SourceXMIElements.Mapper.Stereotypes;
import lombok.*;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

import java.util.ArrayList;
import java.util.List;

@Getter
@Setter
@ToString
public abstract class AbstractXMIComponent implements StereotypeElement {
    private Property properties;
    private List<Tag> tags;


    protected void parseProperty(NodeList properties) {
        Element prop = (Element) properties.item(0);
        this.properties = Property.parse(prop);
    }

    protected void parseTags(NodeList tags) {
        if (tags == null || tags.getLength() == 0) {
            this.tags = new ArrayList<>();
            return;
        }

        Element tagsElement = (Element) tags.item(0);
        NodeList tagList = tagsElement.getElementsByTagName("tag");
        this.tags = Tag.parse(tagList);
    }
    @Override
    public Stereotypes getStereotypeName() {
        return Stereotypes.typeByName(this.getProperties().getStereoType());
    }
}