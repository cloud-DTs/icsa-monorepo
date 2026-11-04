package dtcCharger {
    private import MetaModelDigitalTwin::*;

    #Component def ChargerState_Sensor { }

    // Local trigger only. The Lambda is a no-op placeholder (same as dtcGrid's
    // "greenEnergyUpdate" / dtcPV's "isCycling"): it exists so fed-sysml can
    // reference "dtcCharger.plugUpdate" and generate the Event Registry ->
    // Step Function -> Collector -> Strategy -> Feedback infrastructure.
    // dtcCharger contains NO Battery identifiers - the push target is injected
    // only by federation.
    #Condition def ChargerPlugStrategy {
        #strategyAction plugUpdate :>> strategieActions {
            :>> name = "plugUpdate";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/microgrid/charger/reading";
            :>> external = false;
        }
    }

    #Twin def dtcCharger {
        #entity dtcCharger {
            // Internal charger state.
            //
            // NOT named "state": that is a reserved SysML v2 keyword (state
            // usages/definitions), and using it as an identifier makes the
            // kernel fail to parse the model, which surfaces as
            // "Export path: NOT_FOUND".
            #component chargerState : ChargerState_Sensor {
                // Whether the EV is connected ("true"/"false"). Written by the
                // simulator.
                #measureAttribute isPlugged {
                    :>> dataType default AttributeDataType::STRING;
                }
                // Charging power (kW) currently applied to the EV. Received from
                // the Battery twin via federation - NOT calculated by the Charger.
                #measureAttribute actChargeEV {
                    :>> dataType default AttributeDataType::DOUBLE;
                }
                // Power (kW) the BATTERY is charging itself with. Decided together
                // with actChargeEV and delivered in the SAME feedback message, so
                // one federation covers both halves of the split - no second
                // federation, no duplicated pulls, and nothing written back into
                // dtcBattery.
                #measureAttribute actBatteryCharge {
                    :>> dataType default AttributeDataType::DOUBLE;
                }
            }
            // Maximum charging power the charger hardware can deliver, in kW.
            // Declared at #entity level (NOT inside a #component) because the
            // converter drops #constAttribute nested in a component; entity-level
            // consts materialize as a generated const_component (same as
            // dtc2bat's trueValue/maxTemp).
            #constAttribute maxPower {
                :>> value default "22.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
        }

        :>> hotDatabaseRetentionDays default 30;
        :>> coldDatabaseRetentionDays default 30;

        // Fires on every new isPlugged value (self-comparison, always true - the
        // same idiom as dtcGrid's isReporting). The value is forwarded raw to
        // Battery by the federation push strategy. NOFEEDBACK: the local action
        // publishes nothing.
        #condition plugReporting : ChargerPlugStrategy {
            :>> leftOperand = dtcCharger.chargerState.isPlugged;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcCharger.chargerState.isPlugged;
            :>> plugUpdate {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                isPlugged :>> inputParameters = dtcCharger.chargerState.isPlugged;
            }
        }
    }
}
