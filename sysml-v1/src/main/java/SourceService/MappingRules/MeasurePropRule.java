package SourceService.MappingRules;

import SourceService.SourceXMIElements.Attribute.Attribute;
import SourceService.SourceXMIElements.Connector.Connector;
import SourceService.XMIContext;
import model.TwinComponent;
import model.TwinComponentProperty;
import model.TwinEntity;
import registry.TwinRegistry;

public class MeasurePropRule extends MappingRule<Connector>{
    public MeasurePropRule(XMIContext xmiContext, TwinRegistry twinRegistry) {
        super(xmiContext, twinRegistry);
    }
    @Override
    public boolean matches(Connector element) {
        return false;
    }

    @Override
    public void apply(Connector element) {
        String sourceId = element.getSource().getSourceId();
        String targetId = element.getTarget().getTargetId();

        String attributeGuid = getXmiContext().getTagValue(element,"measurement").get();

        TwinComponent twinComponent = linkComponentAndEntity(sourceId,targetId);

        if(attributeGuid.isEmpty()){
            throw new IllegalArgumentException(String.format("Empty measurement field in connector between device {%s} and component {%s}",
                    twinComponent.getComponentName(),
                    twinComponent.getParentEntity().getEntityName()
                    ));
        }

        addProperty(twinComponent,getXmiContext().getAttribute(attributeGuid),element);
    }

    private void addProperty(TwinComponent twinComponent, Attribute attribute,Connector connector) {
        TwinComponentProperty twinComponentProperty = new TwinComponentProperty();
        twinComponentProperty.setPropertyGuid(attribute.getEaGuid());
        twinComponentProperty.setName(attribute.getName());
        twinComponentProperty.setDataType(getXmiContext().getTagValue(attribute,"dataType").get());


        getTwinRegistry().registerProperty(twinComponent,twinComponentProperty);

    }

    private TwinComponent linkComponentAndEntity(String sourceId, String targetId) {

        boolean sourceIsEntity = getTwinRegistry().getEntity(sourceId) != null;
        boolean targetIsEntity = getTwinRegistry().getEntity(targetId) != null;

        boolean sourceIsComponent = getTwinRegistry().getComponent(sourceId) != null;
        boolean targetIsComponent = getTwinRegistry().getComponent(targetId) != null;

        if(sourceIsEntity && targetIsComponent) {
            return attach(sourceId, targetId);
        }
        if(targetIsEntity && sourceIsComponent) {
            return attach(targetId, sourceId);
        }

        throw new IllegalStateException("Invalid measurement connector: cannot determine component and device!");
    }

    private TwinComponent attach(String entityId, String componentId){
        TwinEntity entity = getTwinRegistry().getEntity(entityId);
        TwinComponent component = getTwinRegistry().getComponent(componentId);

        if(component.getParentEntity() != null && !component.getParentEntity().getId().equals(entity.getId())){
            throw new IllegalStateException(String.format("Failed to connect device {%s} with component {%s}\n"+
                    "Device {%s},measures already {%s}\n" +
                            "A Device can measure exactly one Component",
                    component.getComponentName(),
                    entity.getEntityName(),
                    component.getComponentName(),
                    component.getParentEntity().getEntityName()
                    ));
        }
        component.setParentEntity(entity);
        component.attachToParent();
        return component;
    }

}
