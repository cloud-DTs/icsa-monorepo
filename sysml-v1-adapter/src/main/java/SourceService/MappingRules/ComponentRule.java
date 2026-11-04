package SourceService.MappingRules;

import SourceService.SourceXMIElements.Element.EAElement;
import SourceService.SourceXMIElements.Mapper.Stereotypes;
import SourceService.XMIContext;
import model.TwinEntity;
import registry.TwinRegistry;

public class ComponentRule extends MappingRule<EAElement>{
    public ComponentRule(XMIContext twinMapper, TwinRegistry twinRegistry) {
        super(twinMapper,twinRegistry);
    }

    @Override
    public boolean matches(EAElement element) {
        return element.getStereotypeName().equals(Stereotypes.COMPONENT_INSTANCE);
    }

    @Override
    public void apply(EAElement element) {
        String twinId = element.getOwner();
        EAElement componentDefinition = getXmiContext().findDefinitonBlockForInstance(element);

        if(componentDefinition == null){
            throw new IllegalStateException("No ComponentDefinition found for instance: " + element.getName());
        }

        addComponentInstanceAsSubTwin(element,componentDefinition.getIdref(),twinId);
    }

    private void addComponentInstanceAsSubTwin(EAElement eaElement,String definitionId,String parentId){
        TwinEntity twinEntity = new TwinEntity();
        twinEntity.setEntityId(eaElement.getIdref());
        twinEntity.setEntityName(eaElement.getName());
        twinEntity.setDefinitionId(definitionId);
        twinEntity.setParent(getTwinRegistry().getEntity(parentId));
        twinEntity.attachToParent();

        getTwinRegistry().registerEntity(eaElement.getIdref(),twinEntity);
    }


}
