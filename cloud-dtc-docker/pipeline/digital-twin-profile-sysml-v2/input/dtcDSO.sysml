package dtcDSO {
    private import MetaModelDigitalTwin::*;

    #Component def TransformerSubstation_Sensor { }

    // Trigger-only strategy for TS1 state changes.
    // The real portfolio coordination is performed by the Aggregator federation.
    #Condition def TS1StateUpdateStrategy {
        #strategyAction dsoTS1Update :>> strategieActions {
            :>> name = "dsoTS1Update";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/meps-demo/trigger";
            :>> external = false;
        }
    }

    // Trigger-only strategy for TS2 state changes.
    #Condition def TS2StateUpdateStrategy {
        #strategyAction dsoTS2Update :>> strategieActions {
            :>> name = "dsoTS2Update";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/meps-demo/trigger";
            :>> external = false;
        }
    }

    #Twin def dtcDSO {
        #entity dtcDSO {
            // Transformer substation TS1. EC1 is connected behind this substation.
            #component ts1 : TransformerSubstation_Sensor {
                // Operational network status, e.g. "NORMAL" or "HIGH_VOLTAGE".
                #measureAttribute voltageStatus {
                    :>> dataType default AttributeDataType::STRING;
                }

                // Current signed active-power exchange in MW.
                // Positive = import/absorption from the upstream grid.
                // Negative = export/injection toward the upstream grid.
                #measureAttribute exchangePower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }

                // Current allowed absolute exchange in MW.
                // The MEPSO demo initializes this to 10 MW.
                // It is represented as telemetry/config state so federation
                // can collect it directly together with the TS status.
                #measureAttribute exchangeLimit {
                    :>> dataType default AttributeDataType::DOUBLE;
                }
            }

            // Transformer substation TS2. EC2 is connected behind this substation.
            #component ts2 : TransformerSubstation_Sensor {
                #measureAttribute voltageStatus {
                    :>> dataType default AttributeDataType::STRING;
                }

                #measureAttribute exchangePower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }

                #measureAttribute exchangeLimit {
                    :>> dataType default AttributeDataType::DOUBLE;
                }
            }
        }

        :>> hotDatabaseRetentionDays default 30;
        :>> coldDatabaseRetentionDays default 30;

        // Fires when TS1 voltageStatus is updated.
        // The federation collector also receives the current exchange and limit,
        // so the Aggregator has the complete TS1 constraint state.
        #condition ts1Reporting : TS1StateUpdateStrategy {
            :>> leftOperand = dtcDSO.ts1.voltageStatus;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcDSO.ts1.voltageStatus;
            :>> dsoTS1Update {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                voltageStatus :>> inputParameters = dtcDSO.ts1.voltageStatus;
                exchangePower :>> inputParameters = dtcDSO.ts1.exchangePower;
                exchangeLimit :>> inputParameters = dtcDSO.ts1.exchangeLimit;
            }
        }

        // Fires when TS2 voltageStatus is updated.
        #condition ts2Reporting : TS2StateUpdateStrategy {
            :>> leftOperand = dtcDSO.ts2.voltageStatus;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcDSO.ts2.voltageStatus;
            :>> dsoTS2Update {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                voltageStatus :>> inputParameters = dtcDSO.ts2.voltageStatus;
                exchangePower :>> inputParameters = dtcDSO.ts2.exchangePower;
                exchangeLimit :>> inputParameters = dtcDSO.ts2.exchangeLimit;
            }
        }
    }
}
