package SourceService;

import SourceService.SourceXMIElements.Attribute.Attribute;
import SourceService.SourceXMIElements.Connector.Connector;
import SourceService.SourceXMIElements.Element.EAElement;
import SourceService.SourceXMIElements.Element.Link;
import SourceService.SourceXMIElements.Mapper.Stereotypes;
import SourceService.SourceXMIElements.Tag;
import lombok.Getter;
import lombok.extern.slf4j.Slf4j;

import registry.TwinRegistry;

import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

@Slf4j
@Getter
public class XMIContext {

    private final XMIParser twinParser;

    public XMIContext(XMIParser twinParser) {
        this.twinParser = twinParser;
    }


    public EAElement findDefinitonBlockForInstance(EAElement instance) {
        return twinParser.getOwningAttributes().stream()
                .filter(attr -> attr.getId().equals(instance.getIdref()))
                .findFirst()
                .map(attr -> twinParser.getProfileElementMap().get(attr.getTypeId()))
                .orElse(null);
    }



    public Optional<String> getTagValue(Attribute attribute, String tagName) {
        return attribute.getTags().stream()
                .filter(tag -> tagName.equals(tag.getName()))
                .map(Tag::getValues)
                .findFirst();
    }

    public String getTaggedValue(EAElement element,String taggedValue){

        String value = element.getTags().stream().filter(x -> x.getName().equalsIgnoreCase(taggedValue)).
                findFirst().
                orElseThrow().getValues();

        if(value.contains("#NOTES")){
            return  value.split("#NOTES")[0];
        }
        return value;
    }

    public List<EAElement> getElementsByOwner(Stereotypes stereotype, String ownerId) {
        return Optional.ofNullable(twinParser.getStereoTypeElementMap().get(stereotype))
                .orElse(Collections.emptyList())
                .stream()
                .filter(e -> e.getOwner().equals(ownerId))
                .collect(Collectors.toList());
    }


    public Optional<String> getTagValue(Connector connector, String tagName) {
        return connector.getTags().stream()
                .filter(tag -> tagName.equals(tag.getName()))
                .map(Tag::getValues)
                .findFirst();
    }

    public EAElement getElement(String id){
        return twinParser.getProfileElementMap().get(id);
    }
    public Attribute getAttribute(String id){
        return twinParser.getProfileAttributeMap().get(id);
    }
}
