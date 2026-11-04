package SourceService.MappingRules;

import SourceService.SourceXMIElements.Attribute.Attribute;
import SourceService.SourceXMIElements.Element.EAElement;
import SourceService.XMIContext;
import model.*;
import registry.TwinRegistry;

import java.util.List;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

public class ConstPropRule extends MappingRule<Attribute> {
    public ConstPropRule(XMIContext xmiContext, TwinRegistry twinRegistry) {
        super(xmiContext, twinRegistry);
    }
    @Override
    public boolean matches(Attribute element) {
        return false;
    }

    @Override
    public void apply(Attribute attribute) {
        String definitionId = attribute.getEaGuid();
        EAElement ownerElement = getXmiContext().getElement(attribute.getOwner());


        for(TwinEntity owningEntity: getTwinRegistry().getTwins().stream().filter(x -> x.getDefinitionId().equals(ownerElement.getIdref())).collect(Collectors.toList())){
            addConstProp(attribute,owningEntity,definitionId,getXmiContext().getElement(owningEntity.getId()));
        }
    }

    private void addConstProp(Attribute attribute, TwinEntity owningEntity, String definitionId,EAElement element) {
        String compoundId = "CONST" + owningEntity.getId();

        List<TwinComponent> twinComponents = owningEntity.getComponents().stream()
                .filter(t -> t.getComponentId().equals(compoundId))
                .toList();

        TwinComponent constComponent;

        if (twinComponents.isEmpty()) {
            constComponent = new TwinComponent();
            constComponent.setComponentId(compoundId);
            constComponent.setComponentName("CONST_PROPERTIES");
            constComponent.setDefinitionId(attribute.getEaGuid());
            constComponent.setDeviceId(compoundId);
            constComponent.setParentEntity(owningEntity);
            constComponent.attachToParent();
        } else if (twinComponents.size() == 1) {
            constComponent = twinComponents.getFirst();
        } else {
            throw new IllegalStateException("Only one const component allowed!");
        }

        TwinComponentProperty twinComponentProperty = new TwinComponentProperty();
        twinComponentProperty.setPropertyGuid(definitionId);
        twinComponentProperty.setName(attribute.getName());
        twinComponentProperty.setDataType(getXmiContext().getTagValue(attribute, "dataType").orElse("string"));
        twinComponentProperty.setComponent(constComponent);
        twinComponentProperty.attachToParent();
        twinComponentProperty.setInitialValue(resolveRuntimeValue(element, attribute));


        getTwinRegistry().registerProperty(
                owningEntity.getId(),
                attribute.getEaGuid(),
                twinComponentProperty
        );
    }



    private String resolveRuntimeValue(EAElement instanceElement, Attribute attribute) {

        String runState = Optional.ofNullable(instanceElement.getExtendedRunState()).orElse("");
        if (!runState.isEmpty()) {
            Pattern pattern = Pattern.compile(
                    "Variable=" + Pattern.quote(attribute.getName()) + ";Value=([^;]+);"
            );
            Matcher matcher = pattern.matcher(runState);

            if (matcher.find()) {
                return matcher.group(1);
            }
        }

        if (attribute.getInital_body() != null) {
            return attribute.getInital_body().getBody();
        }

        return "0";
    }
}
