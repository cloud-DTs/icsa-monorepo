package SourceService.MappingRules;

import SourceService.SourceXMIElements.Connector.Connector;
import SourceService.XMIContext;
import model.*;
import registry.TwinRegistry;

import java.util.ArrayList;
import java.util.List;

public class TriggerRule extends MappingRule<Connector> {
    public TriggerRule(XMIContext xmiContext, TwinRegistry twinRegistry) {
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
        String lhsGuid = getXmiContext().getTagValue(element,"lhsProperty").get();
        String rhsGuid = getXmiContext().getTagValue(element,"rhsProperty").get();
        String operator = getXmiContext().getTagValue(element,"operator").get();

        if(operator.isEmpty()){
            operator = "==";
        }

        TwinStrategy twinStrategy = linkStrategyAndComponent(sourceId,targetId);

        TwinComponentProperty lhsProp = getTwinRegistry().getConstProperty(twinStrategy.getComponent().getId(),lhsGuid);
        TwinComponentProperty rhsProp = getTwinRegistry().getConstProperty(twinStrategy.getComponent().getId(),rhsGuid);
        TwinComponentProperty lhsConstProp = getTwinRegistry().getConstProperty(twinStrategy.getComponent().getParentEntity().getId(),lhsGuid);
        TwinComponentProperty rhsConstProp = getTwinRegistry().getConstProperty(twinStrategy.getComponent().getParentEntity().getId(),rhsGuid);

        if(lhsProp == null){
            twinStrategy.setLhs(lhsConstProp);
        }
        else {
            twinStrategy.setLhs(lhsProp);
        }
        if(rhsProp == null){
            twinStrategy.setRhs(rhsConstProp);
        }
        else {
            twinStrategy.setRhs(rhsProp);
        }

        if(twinStrategy.getLhs() == null){
           handleMissingSide(twinStrategy,"lhs",lhsGuid);
        }
        if(twinStrategy.getRhs() == null){
            handleMissingSide(twinStrategy,"rhs",rhsGuid);
        }



        twinStrategy.setOperator(operator);
    }

    private void handleMissingSide(TwinStrategy twinStrategy, String lhs, String lhsGuid) {

        throw new IllegalStateException("Failed to set "+lhs+ " one trigger which triggers strategy "+ twinStrategy.getName() +
                "\nA device can only trigger a startegy with " +
                lhs + " side when the measurementproperty is also measured by the device.\nWhen it is a constproperty it should " +
                "be located in the component, which is measured by the device!" );

    }

    private TwinStrategy linkStrategyAndComponent(String sourceId, String targetId) {
        TwinStrategy twinStrategy = getTwinRegistry().getStrategy(sourceId);
        TwinComponent twinComponent = getTwinRegistry().getComponent(targetId);
        if(twinStrategy == null){
            twinStrategy = getTwinRegistry().getStrategy(targetId);
            twinComponent = getTwinRegistry().getComponent(sourceId);
        }
        if(twinStrategy == null){
            throw new IllegalStateException("A trigger connection is not connected to a StrategyInstance!");
        }

        if( twinComponent == null){
            throw new IllegalStateException("A trigger connection is not connected to a DeviceInstance!");

        }



        twinStrategy.setComponent(twinComponent);
        twinStrategy.attachToParent();

        return twinStrategy;
    }
}
