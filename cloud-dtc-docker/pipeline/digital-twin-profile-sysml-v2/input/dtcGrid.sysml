package dtcGrid {
    private import MetaModelDigitalTwin::*;

    #Component def Grid_Sensor { }

    #Condition def GridReadingStrategy {
        #strategyAction greenEnergyUpdate :>> strategieActions {
            :>> name = "greenEnergyUpdate";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/microgrid/grid/reading";
            :>> external = false;
        }
    }

    // Independent trigger strategyAction for the SECOND (maxPower) federation.
    // Reuses the same no-op grid/reading Lambda; it exists only so fed-sysml can
    // reference "dtcGrid.maxPowerUpdate". Separate from GridReadingStrategy so the
    // greenEnergy federation is unaffected.
    #Condition def GridMaxPowerStrategy {
        #strategyAction maxPowerUpdate :>> strategieActions {
            :>> name = "maxPowerUpdate";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/microgrid/grid/reading";
            :>> external = false;
        }
    }

    #Twin def dtcGrid {
        #entity dtcGrid {
            #component sensor : Grid_Sensor {
                // Current percentage of renewable/green energy available in the grid (0-100).
                #measureAttribute greenEnergyPercentage {
                    :>> dataType default AttributeDataType::DOUBLE;
                }
                // Current electricity price, in EUR/kWh.
                #measureAttribute currentElectricityPrice {
                    :>> dataType default AttributeDataType::DOUBLE;
                }
                // Maximum allowed grid load/threshold limit.
                #measureAttribute gridLimit {
                    :>> dataType default AttributeDataType::DOUBLE;
                }
                // Available external power the grid can currently provide, in kW.
                // Forwarded raw to Battery by the maxPower federation.
                #measureAttribute maxPower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }
            }
        }

        :>> hotDatabaseRetentionDays default 30;
        :>> coldDatabaseRetentionDays default 30;

        // Fires on every new greenEnergyPercentage measurement (same always-true,
        // self-comparison idiom used by dtc2pv's "isGenerating"). Every value is
        // forwarded by the federation push strategy below - no previous-state
        // check, no threshold-crossing detection.
        #condition isReporting : GridReadingStrategy {
            :>> leftOperand = dtcGrid.sensor.greenEnergyPercentage;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcGrid.sensor.greenEnergyPercentage;
            :>> greenEnergyUpdate {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                greenEnergyPercentage :>> inputParameters = dtcGrid.sensor.greenEnergyPercentage;
            }
        }

        // Independent trigger for the maxPower federation - fires on every new
        // maxPower value (self-comparison), forwarded raw. Fully separate from
        // isReporting/greenEnergyUpdate above.
        #condition maxPowerReporting : GridMaxPowerStrategy {
            :>> leftOperand = dtcGrid.sensor.maxPower;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcGrid.sensor.maxPower;
            :>> maxPowerUpdate {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                maxPower :>> inputParameters = dtcGrid.sensor.maxPower;
            }
        }
    }
}
