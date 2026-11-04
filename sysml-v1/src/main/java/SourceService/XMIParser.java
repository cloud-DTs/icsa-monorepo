package SourceService;

import SourceService.SourceXMIElements.Attribute.Attribute;
import SourceService.SourceXMIElements.Attribute.Stereotype;
import SourceService.SourceXMIElements.Connector.Connector;
import SourceService.SourceXMIElements.Element.EAElement;
import SourceService.SourceXMIElements.Mapper.Stereotypes;
import SourceService.SourceXMIElements.OwningAttribute.OwningAttribute;
import SourceService.SourceXMIElements.Property;
import lombok.Getter;
import lombok.Setter;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

import java.util.*;

@Getter
@Setter
public class XMIParser {

    private final Map<String, EAElement> profileElementMap = new HashMap<>();
    private final Map<String, Connector> profileConnectorMap = new HashMap<>();
    private final Map<String, Attribute> profileAttributeMap = new HashMap<>();

    private final Map<Stereotypes, List<EAElement>> stereoTypeElementMap = new HashMap<>();
    private final Map<Stereotypes, List<Connector>> stereoTypeConnectorMap = new HashMap<>();
    private final Map<Stereotypes, List<Attribute>> stereoTypeAttributeMap = new HashMap<>();

    private final List<EAElement> elementList = new ArrayList<>();
    private final List<Connector> connectorList = new ArrayList<>();
    private final List<Attribute> attributeList = new ArrayList<>();
    private final List<OwningAttribute> owningAttributes = new ArrayList<>();


    private void addAttribute(Attribute attribute,String ownerId) {
        if (attribute == null || attribute.getStereotype() == null) return;

        Stereotypes stereotype = Stereotypes.typeByName(attribute.getStereotype().getStereotype());
        if (stereotype == null) return;

        attributeList.add(attribute);
        profileAttributeMap.put(attribute.getEaGuid(), attribute);
        attribute.setOwner(ownerId);
        stereoTypeAttributeMap
                .computeIfAbsent(stereotype, k -> new ArrayList<>())
                .add(attribute);
    }

    private void addElement(Element element) {
        EAElement eaElement = EAElement.parse(element);
        if (eaElement == null || eaElement.getProperties() == null) return;

        Stereotypes stereotype = Stereotypes.typeByName(eaElement.getProperties().getStereoType());
        if (stereotype == null) return;

        elementList.add(eaElement);
        profileElementMap.put(eaElement.getIdref(), eaElement);

        stereoTypeElementMap
                .computeIfAbsent(stereotype, k -> new ArrayList<>())
                .add(eaElement);

        if (eaElement.getAttributes() != null) {
            eaElement.getAttributes().forEach(x->this.addAttribute(x,eaElement.getIdref()));
        }
    }

    private void addConnector(Element element) {
        Connector connector = Connector.parse(element);
        if (connector == null || connector.getProperties() == null) return;

        Stereotypes stereotype = Stereotypes.typeByName(connector.getProperties().getStereoType());
        if (stereotype == null) return;

        connectorList.add(connector);
        profileConnectorMap.put(connector.getIdref(), connector);

        stereoTypeConnectorMap
                .computeIfAbsent(stereotype, k -> new ArrayList<>())
                .add(connector);
    }
    public void parse(NodeList elements, NodeList connectors,NodeList owningAttributes) {
        for (int i = 0; i < elements.getLength(); i++) {
            addElement((Element) elements.item(i));
        }
        for (int i = 0; i < connectors.getLength(); i++) {
            addConnector((Element) connectors.item(i));
        }
        for (int i = 0; i < owningAttributes.getLength(); i++) {
            this.owningAttributes.add(OwningAttribute.parse((Element) owningAttributes.item(i)));
        }
    }
}
