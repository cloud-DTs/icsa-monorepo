package SourceService.SourceXMIElements.Connector;

import SourceService.SourceXMIElements.AbstractXMIComponent;
import SourceService.SourceXMIElements.Mapper.Stereotypes;
import SourceService.SourceXMIElements.Tag;
import lombok.*;
import org.w3c.dom.Element;

@Getter
@Setter
@NoArgsConstructor
@ToString(callSuper = true)
public class Connector extends AbstractXMIComponent {
    private String idref;
    private Source source;
    private Target target;


    public static Connector parse(Element element) {
        Connector connector = new Connector();
        connector.idref = element.getAttribute("xmi:idref");
        connector.source = Source.parse((Element) element.getElementsByTagName("source").item(0));
        connector.target = Target.parse((Element) element.getElementsByTagName("target").item(0));
        connector.parseProperty(element.getElementsByTagName("properties"));
        connector.setTags(Tag.parse(element.getElementsByTagName("tag")));
        return connector;
    }

}