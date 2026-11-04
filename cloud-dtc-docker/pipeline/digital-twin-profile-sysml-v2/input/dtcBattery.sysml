package dtcBattery {
    private import MetaModelDigitalTwin::*;

    #Component def BatteryStorage_Sensor { }
    #Component def BatteryExternalInput_Sensor { }

    // Local trigger only. The Lambda is a no-op placeholder (same as dtcGrid's
    // "greenEnergyUpdate"): it exists so fed-sysml can reference
    // "dtcBattery.plugDecision" and generate the Event Registry -> Step Function
    // -> Collector -> Strategy -> Feedback infrastructure. The charging decision
    // itself runs in the federation-owned Strategy Lambda - a twin-owned
    // NOFEEDBACK action has no way to write another twin.
    //
    // Named plugDecision (not plugUpdate) purely so it is distinguishable from
    // dtcCharger's plugUpdate in CloudWatch logs. The SSM registry keys are
    // namespaced per twin, so there would be no collision either way.
    #Condition def BatteryPlugDecisionStrategy {
        #strategyAction plugDecision :>> strategieActions {
            :>> name = "plugDecision";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/microgrid/battery/decision-trigger";
            :>> external = false;
        }
    }

    // Second decision trigger: the PV surplus point. Reuses the same no-op
    // trigger Lambda - only the condition differs.
    //
    // Unlike every other condition in this project this one is NOT a
    // self-comparison: it compares generatedPower against a constant, so
    // event-checker fires it ONLY when the value actually equals the threshold.
    // That keeps ordinary PV pushes from starting a Step Function at all.
    #Condition def BatterySurplusStrategy {
        #strategyAction surplusDecision :>> strategieActions {
            :>> name = "surplusDecision";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/microgrid/battery/decision-trigger";
            :>> external = false;
        }
    }

    // Third decision trigger: favourable renewable conditions in the grid. Same
    // no-op trigger Lambda, conditional like BatterySurplusStrategy - it fires
    // only when greenEnergyPercentage actually exceeds the threshold.
    #Condition def BatteryGreenEnergyStrategy {
        #strategyAction greenEnergyDecision :>> strategieActions {
            :>> name = "greenEnergyDecision";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/microgrid/battery/decision-trigger";
            :>> external = false;
        }
    }

    #Twin def dtcBattery {
        #entity dtcBattery {
            // Internal battery state (measured at runtime). Same pattern as
            // dtc2bat's p16 component.
            #component storage : BatteryStorage_Sensor {
                // Current battery charge level, in percent (0-100).
                #measureAttribute charge {
                    :>> dataType default AttributeDataType::DOUBLE;
                }
                // Whether the battery/charger connection is active ("true"/"false").
                #measureAttribute isPlugged {
                    :>> dataType default AttributeDataType::STRING;
                }
                // Current state: "charging" / "discharging" / "idle". Decided
                // internally by the battery (not written by any federation).
                #measureAttribute chargingStatus {
                    :>> dataType default AttributeDataType::STRING;
                }
                // How much of the delivered power is actually bought from the
                // grid, in kW. Zero while the grid is brown (nothing is bought -
                // the car runs off the battery and PV). While it is green this
                // is what remains after PV covers its share, so more sun means a
                // smaller number.
                //
                // Written by the decision federation into the SAME message as
                // charge, so it costs no extra device and no extra publish.
                #measureAttribute gridPower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }
            }
            // External inputs received from other twins via federation. Same
            // pattern as dtc2bat's pvInput virtual-sensor component - these are
            // written by push/request federations, not produced locally.
            #component externalInputs : BatteryExternalInput_Sensor {
                // From the PV twin.
                #measureAttribute generatedPower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }
                // From the Grid twin.
                #measureAttribute greenEnergyPercentage {
                    :>> dataType default AttributeDataType::DOUBLE;
                }
                // From the Grid twin.
                #measureAttribute electricityPrice {
                    :>> dataType default AttributeDataType::DOUBLE;
                }
                // Available external power - provided dynamically by Grid/PV/another
                // twin. NOT a battery constant (the battery does not know the
                // available external power).
                #measureAttribute maxPower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }
            }
            // Static battery configuration (fixed specifications). Declared at the
            // #entity level - NOT inside a component - because the converter drops
            // #constAttribute nested in a component; entity-level consts materialize
            // as a generated const_component (same as dtc2bat's trueValue/maxTemp).
            // Default values are placeholders - adjust to the real battery spec.
            // Usable energy store, in kWh. Sized for a commercial charging site
            // (22 kW charger, 10 kW PV, 25 kW grid connection), not a household
            // battery: at 10 kW it must survive the eight-hour evening stretch
            // between the 13:00 and 21:00 scenarios without hitting the reserve.
            #constAttribute totalCapacity {
                :>> value default "200.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute maxChargingPower {
                :>> value default "10.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute maxDischargingPower {
                :>> value default "10.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            // NOT USED IN ANY CONDITION ANY MORE. The conditions below are pure
            // triggers now, and the thresholds that decide the outcome live in
            // decision_logic.py (GREEN_ENERGY_THRESHOLD = 75.0). Kept only so the
            // values stay visible on the twin; the authoritative copy is the
            // Python one. Do not reintroduce them into a condition without
            // syncing both places.
            #constAttribute surplusThreshold {
                :>> value default "47.5";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute greenEnergyThreshold {
                :>> value default "75.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            // The "plugged in" value, used as the right-hand side of the plug
            // condition so that it compares against a constant instead of
            // against itself. The Charger push Lambda normalises every plug
            // state to exactly "true"/"false", so this matches reliably.
            #constAttribute pluggedTrue {
                :>> value default "true";
                :>> dataType default AttributeDataType::STRING;
            }
        }

        :>> hotDatabaseRetentionDays default 30;
        :>> coldDatabaseRetentionDays default 30;

        // ------------------------------------------------------------------ //
        // Three decision triggers, one per input that can change the outcome.
        //
        // The deployed event-checker filters by the property that actually
        // arrived in the message:
        //
        //     trigger_keys = set(event.keys()) - {"iotDeviceId", "time"}
        //     if not trigger_keys.intersection(condition_properties): skip
        //
        // That is why the self-comparison idiom is safe here: each condition
        // only ever fires on ITS OWN property. A `charge` message from the
        // simulator matches none of them and starts nothing.
        //
        // The decision itself (green >= 75%, car priority, power split) lives in
        // decision_logic.py - these conditions are pure triggers, not policy.
        // ------------------------------------------------------------------ //

        // Fires when a new plug state arrives from the Charger push, and only
        // when it is "true" - unplugging does not start a decision.
        //
        // NOFEEDBACK: the local action publishes nothing; the federation
        // Feedback Lambda writes actChargeEV to dtcCharger.
        #condition plugDecisionReport : BatteryPlugDecisionStrategy {
            :>> leftOperand = dtcBattery.storage.isPlugged;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcBattery.pluggedTrue;
            :>> plugDecision {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                isPlugged :>> inputParameters = dtcBattery.storage.isPlugged;
            }
        }

        // Fires on every new generatedPower value pushed in from the PV twin.
        // Self-comparison on purpose: any new production figure changes the
        // power split, so every one of them must re-run the decision.
        #condition surplusReport : BatterySurplusStrategy {
            :>> leftOperand = dtcBattery.externalInputs.generatedPower;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcBattery.externalInputs.generatedPower;
            :>> surplusDecision {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                generatedPower :>> inputParameters = dtcBattery.externalInputs.generatedPower;
            }
        }

        // Fires on every new greenEnergyPercentage value pushed in from the Grid
        // twin. Whether the grid counts as green (>= 75%) is decided in
        // decision_logic.py, not here - this is only the trigger.
        #condition greenEnergyReport : BatteryGreenEnergyStrategy {
            :>> leftOperand = dtcBattery.externalInputs.greenEnergyPercentage;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcBattery.externalInputs.greenEnergyPercentage;
            :>> greenEnergyDecision {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                greenEnergyPercentage :>> inputParameters = dtcBattery.externalInputs.greenEnergyPercentage;
            }
        }
    }
}
