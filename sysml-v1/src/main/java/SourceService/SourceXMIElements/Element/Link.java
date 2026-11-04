package SourceService.SourceXMIElements.Element;

import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

import java.util.ArrayList;
import java.util.List;

@Setter
@Getter
@NoArgsConstructor
public class Link {
    private String id;
    private String startId;
    private  String endId;


    public static Link parse(Element element){
        if(element == null){
            return  null;
        }

        Link link = new Link();
        link.id = element.getAttribute("xmi:id");
        link.startId = element.getAttribute("start");
        link.endId = element.getAttribute("end");
        return link;
    }

    public static List<Link> parse(NodeList nodeList){
        List<Link> links =new ArrayList<>();
        if(nodeList == null){
            return  null;
        }
        for(int i = 0; i < nodeList.getLength(); i++){
            Element element = (Element) nodeList.item(i);
            Link link = Link.parse(element);
            links.add(link);
        }
        return links;
    }
}
