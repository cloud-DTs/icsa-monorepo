package SourceService.SourceXMIElements.Connector;

import SourceService.SourceXMIElements.Tag;
import lombok.*;
import org.w3c.dom.Element;
import org.w3c.dom.Node;

import java.util.List;

@Getter
@Setter
@NoArgsConstructor
@ToString
public class Target {
    private String targetId;
    private List<Tag> tags;
    private String role_name;


    public static Target parse(Element element) {
        if(element == null){
            return null;
        }
        Target target = new Target();
        target.targetId = element.getAttribute("xmi:idref");
        target.tags = Tag.parse(element.getElementsByTagName("tags"));
        Element role = (Element) element.getElementsByTagName("role").item(0);
        if (role != null) {
            target.role_name = role.getAttribute("name");
        }
        return target;
    }
}
