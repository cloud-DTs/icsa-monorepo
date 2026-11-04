package SourceService.SourceXMIElements;

import lombok.*;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

import java.util.ArrayList;
import java.util.List;

@Getter
@Setter
@NoArgsConstructor
@ToString(callSuper = true)
public class Tag {
    private String xmi_id;
    private String name;
    private String values;
    private String notes;

    public static Tag parse(Element item) {
        Tag tag = new Tag();
        tag.xmi_id = item.getAttribute("xmi:id");
        tag.name = item.getAttribute("name");
        tag.values = item.getAttribute("value");
        tag.notes = item.getAttribute("notes");

        return tag;
    }

    public static List<Tag> parse(NodeList elements){
        List<Tag> tags = new ArrayList<>();

        for (int i = 0; i < elements.getLength(); i++) {
            tags.add(parse((Element) elements.item(i)));
        }
        return tags;

    }
}