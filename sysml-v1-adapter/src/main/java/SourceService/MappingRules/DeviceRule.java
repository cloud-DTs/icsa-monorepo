package SourceService.MappingRules;

import SourceService.SourceXMIElements.Element.EAElement;
import SourceService.SourceXMIElements.Mapper.Stereotypes;
import SourceService.XMIContext;
import model.TwinComponent;
import registry.TwinRegistry;

public class DeviceRule extends MappingRule<EAElement>{
    public DeviceRule(XMIContext xmiContext, TwinRegistry twinRegistry) {
        super(xmiContext, twinRegistry);
    }

    @Override
    public boolean matches(EAElement element) {
        return element.getStereotypeName().equals(Stereotypes.DEVICE_INSTANCE);
    }

    @Override
    public void apply(EAElement element) {
        EAElement deviceDefinition = getXmiContext().findDefinitonBlockForInstance(element);

        if(deviceDefinition == null){
            throw new IllegalStateException("No DeviceDefinition found for instance: " + element.getName());
        }

        addDevice(element,deviceDefinition);
    }

    private void addDevice(EAElement element, EAElement deviceDefinition) {
        TwinComponent twinComponent = new TwinComponent();
        twinComponent.setComponentId(element.getIdref());
        twinComponent.setComponentName(element.getName());
        twinComponent.setDefinitionId(deviceDefinition.getIdref());
        twinComponent.setDeviceId(element.getIdref());
        getTwinRegistry().registerComponent(element.getIdref(), twinComponent);
    }
}
