package SourceService.SourceXMIElements.Attribute;

import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import lombok.ToString;
import org.w3c.dom.Element;
@Getter
@Setter
@ToString(callSuper = true)
@NoArgsConstructor
public class Initial {
    private String body;

    public static Initial parse(Element element) {
        Initial initial = new Initial();
        initial.body = element.getAttribute("body");
        return initial;
    }
}
