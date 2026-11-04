package SourceService.MappingRules;

import SourceService.SourceXMIElements.Connector.Connector;
import SourceService.XMIContext;
import model.TwinComponent;
import model.TwinStrategy;
import registry.TwinRegistry;

public class FeedBackRule extends MappingRule<Connector> {
    public FeedBackRule(XMIContext xmiContext, TwinRegistry twinRegistry) {
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

        TwinStrategy twinStrategy = getTwinRegistry().getStrategy(sourceId);
        TwinComponent twinComponent = getTwinRegistry().getComponent(targetId);

        if(twinStrategy == null){
            twinStrategy = getTwinRegistry().getStrategy(targetId);
            twinComponent = getTwinRegistry().getComponent(sourceId);
        }
        if(twinStrategy == null || twinComponent == null){
            throw new IllegalStateException("Strategy or Component not found for a feedBack connector;");

        }
        twinStrategy.getFeedBack().setTopic(twinComponent.getComponentId());
    }
}
