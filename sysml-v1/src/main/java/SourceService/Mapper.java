package SourceService;

import SourceService.MappingRules.*;
import SourceService.SourceXMIElements.Attribute.Attribute;
import SourceService.SourceXMIElements.Connector.Connector;
import SourceService.SourceXMIElements.Element.EAElement;
import SourceService.SourceXMIElements.Mapper.Stereotypes;
import model.TwinEntity;
import registry.TwinRegistry;

import java.util.List;

public class Mapper {

    public XMIParser twinParser;
    public TwinRegistry twinRegistry;
    public XMIContext xmiContext;


    public Mapper(XMIParser twinParser, TwinRegistry twinRegistry, XMIContext xmiContext) {
        this.twinParser = twinParser;
        this.twinRegistry = twinRegistry;
        this.xmiContext = xmiContext;
    }


    public List<TwinEntity> parse(){
        TwinRule twinRule = new TwinRule(xmiContext,twinRegistry);
        ComponentRule componentRule = new ComponentRule(xmiContext,twinRegistry);
        DeviceRule deviceRule = new DeviceRule(xmiContext,twinRegistry);
        StrategyRule strategyRule = new StrategyRule(xmiContext,twinRegistry);
        ConstPropRule constPropRule = new ConstPropRule(xmiContext,twinRegistry);
        MeasurePropRule meaPropRule = new MeasurePropRule(xmiContext,twinRegistry);
        TriggerRule triggerRule = new TriggerRule(xmiContext,twinRegistry);
        FeedBackRule feedBackRule = new FeedBackRule(xmiContext,twinRegistry);

        for(EAElement e : twinParser.getStereoTypeElementMap().getOrDefault(Stereotypes.TWIN, List.of()))
            twinRule.apply(e);
        for(EAElement e : twinParser.getStereoTypeElementMap().getOrDefault(Stereotypes.COMPONENT_INSTANCE, List.of()))
            componentRule.apply(e);
        for(EAElement e : twinParser.getStereoTypeElementMap().getOrDefault(Stereotypes.DEVICE_INSTANCE, List.of()))
            deviceRule.apply(e);
        for(EAElement e : twinParser.getStereoTypeElementMap().getOrDefault(Stereotypes.STRATEGY_INSTANCE, List.of()))
            strategyRule.apply(e);

        for(Attribute a : twinParser.getStereoTypeAttributeMap().getOrDefault(Stereotypes.CONST_INSTANCE, List.of()))
            constPropRule.apply(a);

        for(Connector c : twinParser.getStereoTypeConnectorMap().getOrDefault(Stereotypes.MEASURES, List.of()))
            meaPropRule.apply(c);
        for(Connector c : twinParser.getStereoTypeConnectorMap().getOrDefault(Stereotypes.TRIGGERS, List.of()))
            triggerRule.apply(c);
        for(Connector c : twinParser.getStereoTypeConnectorMap().getOrDefault(Stereotypes.FEEDBACK_TOPIC, List.of()))
            feedBackRule.apply(c);

        return twinRegistry.getTwins().stream().filter(x->x.getDefinitionId().equals(x.getId())).toList();
    }

}
