package SourceService.SourceXMIElements.Connector;

import SourceService.SourceXMIElements.Tag;
import lombok.*;
import org.w3c.dom.Element;
import org.w3c.dom.Node;


import java.util.ArrayList;
import java.util.List;

@Getter
@Setter
@NoArgsConstructor
@ToString
public class Source {
    private String sourceId;
    private List<Tag> tags;
    private String role_name;

    public static Source parse(Element element) {
        if(element == null) {
            return null;
        }
        Source source = new Source();
        source.sourceId = element.getAttribute("xmi:idref");
        source.tags = Tag.parse(element.getElementsByTagName("tags"));
        Element role = (Element) element.getElementsByTagName("role").item(0);
        if (role != null) {
            source.role_name = role.getAttribute("name");
        }
        return source;
    }

}


