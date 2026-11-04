package dtcPV {
    private import MetaModelDigitalTwin::*;

    #Component def PV_Panel_Sensor { }

    // Local trigger strategyAction only. Its Lambda is a no-op placeholder (like
    // dtc2pv's "production" / dtcGrid's "greenEnergyUpdate"): it exists so
    // fed-sysml can reference "dtcPV.isCycling" and generate the Event Registry
    // -> Step Function -> Collector -> Strategy -> Feedback infrastructure. dtcPV
    // itself contains NO Weather identifiers - the request-response logic lives in
    // the federation-owned Strategy Lambda, enabled only by federation.
    #Condition def PVCycleStrategy {
        #strategyAction isCycling :>> strategieActions {
            :>> name = "isCycling";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/microgrid/pv/cycle-trigger";
            :>> external = false;
        }
    }

    // Trigger strategyAction for the PV -> Battery generatedPower push federation.
    // Reuses the same no-op cycle-trigger Lambda; it exists only so fed-sysml can
    // reference "dtcPV.productionUpdate". Separate from PVCycleStrategy so the
    // PV-Weather flow is unaffected.
    #Condition def PVProductionStrategy {
        #strategyAction productionUpdate :>> strategieActions {
            :>> name = "productionUpdate";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/microgrid/pv/cycle-trigger";
            :>> external = false;
        }
    }

    #Twin def dtcPV {
        #entity dtcPV {
            #component panel : PV_Panel_Sensor {
                // Current simulation hour (0-23, then restarts), written by the
                // simulator cycle mode. The federation trigger.
                #measureAttribute hours_cycle {
                    :>> dataType default AttributeDataType::INTEGER;
                }
                // Calculated production, in kW. Written back by the PV-Weather
                // Feedback Lambda; visible in Grafana. Also the trigger source for
                // the PV -> Battery generatedPower push (productionReport below).
                #measureAttribute production {
                    :>> dataType default AttributeDataType::DOUBLE;
                }
            }
            // Maximum PV production capacity, in kW (~50 kW parking canopy).
            // Declared at #entity level (NOT inside a #component) because the
            // converter drops #constAttribute nested in a component - it only
            // materializes entity-level consts, as a generated const_component
            // (same as dtc2bat's trueValue/maxTemp).
            #constAttribute maxPower {
                :>> value default "10.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
        }

        :>> hotDatabaseRetentionDays default 30;
        :>> coldDatabaseRetentionDays default 30;

        // Fires on every new hours_cycle value (self-comparison, always true).
        // Collector fetches ONLY hours_cycle (a measure). maxPower is a static
        // const and is injected as an env var by the federation enablement step
        // (read from the generated const_component's initValue), NOT collected -
        // no working federation collects a const, and a single strategyAction
        // taking two inputParameters is unprecedented. NOFEEDBACK: the local
        // action publishes nothing; the federation Feedback Lambda writes
        // production back to dtcPV.
        #condition cycleReport : PVCycleStrategy {
            :>> leftOperand = dtcPV.panel.hours_cycle;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcPV.panel.hours_cycle;
            :>> isCycling {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                hours_cycle :>> inputParameters = dtcPV.panel.hours_cycle;
            }
        }

        // Fires on every new production value (self-comparison). Forwards the raw
        // production to Battery.generatedPower via the PV -> Battery federation.
        // No self-loop: this triggers the PV->Battery push (which writes Battery),
        // not the PV-Weather flow (which writes this production).
        #condition productionReport : PVProductionStrategy {
            :>> leftOperand = dtcPV.panel.production;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcPV.panel.production;
            :>> productionUpdate {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                production :>> inputParameters = dtcPV.panel.production;
            }
        }
    }
}
