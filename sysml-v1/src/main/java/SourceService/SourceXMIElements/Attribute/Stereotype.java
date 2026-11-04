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
public class Stereotype {
    private String stereotype;

    public static Stereotype parse(Element element) {
        if(element == null){
            return new Stereotype();
        }
        Stereotype stereotype = new Stereotype();
        stereotype.setStereotype(element.getAttribute("stereotype"));
        return stereotype;
    }

}
