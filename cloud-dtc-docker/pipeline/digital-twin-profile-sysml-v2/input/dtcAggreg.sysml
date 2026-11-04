package dtcAggreg {
    private import MetaModelDigitalTwin::*;

    #Component def AggregatorTSOInput_Component { }
    #Component def AggregatorDSOInput_Component { }
    #Component def AggregatorECInput_Component { }
    #Component def AggregatorDecision_Component { }

    // --------------------------------------------------------------------- //
    // Decision triggers.
    //
    // These local strategy actions only emit federation trigger events. They do not calculate dispatch or modify twin state. The real MEPSO dispatch policy is implemented by the federation-owned Strategy Lambda.
    // --------------------------------------------------------------------- //

    #Condition def AggregatorTSOInputStrategy {
        #strategyAction aggregatorTSOUpdate :>> strategieActions {
            :>> name = "aggregatorTSOUpdate";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/meps-demo/trigger";
            :>> external = false;
        }
    }

    #Condition def AggregatorDSOTS1InputStrategy {
        #strategyAction aggregatorDSOTS1Update :>> strategieActions {
            :>> name = "aggregatorDSOTS1Update";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/meps-demo/trigger";
            :>> external = false;
        }
    }

    #Condition def AggregatorDSOTS2InputStrategy {
        #strategyAction aggregatorDSOTS2Update :>> strategieActions {
            :>> name = "aggregatorDSOTS2Update";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/meps-demo/trigger";
            :>> external = false;
        }
    }

    #Condition def AggregatorEC1BatteryInputStrategy {
        #strategyAction aggregatorEC1BatteryUpdate :>> strategieActions {
            :>> name = "aggregatorEC1BatteryUpdate";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/meps-demo/trigger";
            :>> external = false;
        }
    }

    #Condition def AggregatorEC1PVInputStrategy {
        #strategyAction aggregatorEC1PVUpdate :>> strategieActions {
            :>> name = "aggregatorEC1PVUpdate";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/meps-demo/trigger";
            :>> external = false;
        }
    }

    #Condition def AggregatorEC1DSRInputStrategy {
        #strategyAction aggregatorEC1DSRUpdate :>> strategieActions {
            :>> name = "aggregatorEC1DSRUpdate";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/meps-demo/trigger";
            :>> external = false;
        }
    }

    #Condition def AggregatorEC2BatteryInputStrategy {
        #strategyAction aggregatorEC2BatteryUpdate :>> strategieActions {
            :>> name = "aggregatorEC2BatteryUpdate";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/meps-demo/trigger";
            :>> external = false;
        }
    }

    #Condition def AggregatorEC2PVInputStrategy {
        #strategyAction aggregatorEC2PVUpdate :>> strategieActions {
            :>> name = "aggregatorEC2PVUpdate";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/meps-demo/trigger";
            :>> external = false;
        }
    }

    #Condition def AggregatorEC2DSRInputStrategy {
        #strategyAction aggregatorEC2DSRUpdate :>> strategieActions {
            :>> name = "aggregatorEC2DSRUpdate";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/meps-demo/trigger";
            :>> external = false;
        }
    }

    // --------------------------------------------------------------------- //
    // Direct EC and DSO telemetry triggers.
    //
    // The Aggregator decision federation writes all calculated power values
    // atomically and increments decisionVersion. Its update triggers six
    // federation strategies because every target is a separate IoT device.
    // --------------------------------------------------------------------- //

    #Condition def AggregatorEC1BatteryDecisionUpdateStrategy {
        #strategyAction decisionEC1BatteryUpdate :>> strategieActions {
            :>> name = "decisionEC1BatteryUpdate";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/meps-demo/trigger";
            :>> external = false;
        }
    }

    #Condition def AggregatorEC1DSRDecisionUpdateStrategy {
        #strategyAction decisionEC1DSRUpdate :>> strategieActions {
            :>> name = "decisionEC1DSRUpdate";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/meps-demo/trigger";
            :>> external = false;
        }
    }

    #Condition def AggregatorEC2BatteryDecisionUpdateStrategy {
        #strategyAction decisionEC2BatteryUpdate :>> strategieActions {
            :>> name = "decisionEC2BatteryUpdate";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/meps-demo/trigger";
            :>> external = false;
        }
    }

    #Condition def AggregatorEC2DSRDecisionUpdateStrategy {
        #strategyAction decisionEC2DSRUpdate :>> strategieActions {
            :>> name = "decisionEC2DSRUpdate";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/meps-demo/trigger";
            :>> external = false;
        }
    }

    #Condition def AggregatorTS1ExchangeDecisionUpdateStrategy {
        #strategyAction decisionTS1ExchangeUpdate :>> strategieActions {
            :>> name = "decisionTS1ExchangeUpdate";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/meps-demo/trigger";
            :>> external = false;
        }
    }

    #Condition def AggregatorTS2ExchangeDecisionUpdateStrategy {
        #strategyAction decisionTS2ExchangeUpdate :>> strategieActions {
            :>> name = "decisionTS2ExchangeUpdate";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/meps-demo/trigger";
            :>> external = false;
        }
    }

    #Twin def dtcAggreg {
        #entity dtcAggreg {

            // Current request received from the MEPSO / TSO twin.
            #component tsoInput : AggregatorTSOInput_Component {
                #measureAttribute requestedPower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }

                #measureAttribute serviceDirection {
                    :>> dataType default AttributeDataType::STRING;
                }

                #measureAttribute serviceType {
                    :>> dataType default AttributeDataType::STRING;
                }
            }

            // Current DSO constraints and transformer-substation state.
            #component dsoInput : AggregatorDSOInput_Component {
                #measureAttribute ts1VoltageStatus {
                    :>> dataType default AttributeDataType::STRING;
                }

                // Positive = import/absorption; negative = export/injection.
                #measureAttribute ts1ExchangePower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }

                #measureAttribute ts1ExchangeLimit {
                    :>> dataType default AttributeDataType::DOUBLE;
                }

                #measureAttribute ts2VoltageStatus {
                    :>> dataType default AttributeDataType::STRING;
                }

                #measureAttribute ts2ExchangePower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }

                #measureAttribute ts2ExchangeLimit {
                    :>> dataType default AttributeDataType::DOUBLE;
                }
            }

            // Current EC1 portfolio state received through federation.
            #component ec1Input : AggregatorECInput_Component {
                #measureAttribute ec1BatteryStateOfCharge {
                    :>> dataType default AttributeDataType::DOUBLE;
                }

                // Positive = charging; negative = discharging.
                #measureAttribute ec1BatteryPower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }

                #measureAttribute ec1PVPower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }

                // Positive = increased demand; negative = reduced demand.
                #measureAttribute ec1DSRPower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }
            }

            // Current EC2 portfolio state received through federation.
            #component ec2Input : AggregatorECInput_Component {
                #measureAttribute ec2BatteryStateOfCharge {
                    :>> dataType default AttributeDataType::DOUBLE;
                }

                #measureAttribute ec2BatteryPower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }

                #measureAttribute ec2PVPower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }

                #measureAttribute ec2DSRPower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }
            }

            // One device owns the complete atomic decision before its power
            // values are forwarded directly into the EC telemetry components.
            #component decision : AggregatorDecision_Component {
                #measureAttribute ec1BatteryPower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }

                #measureAttribute ec1DSRPower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }

                #measureAttribute ec2BatteryPower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }

                #measureAttribute ec2DSRPower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }

                // Delivered service magnitude in MW. Direction is stored separately in deliveredServiceDirection.
                #measureAttribute deliveredPower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }

                #measureAttribute deliveredServiceDirection {
                    :>> dataType default AttributeDataType::STRING;
                }

                // Resulting exchange at each transformer substation.
                #measureAttribute ts1ExchangePower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }

                #measureAttribute ts2ExchangePower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }

                // Human-readable decision mode for the demo/dashboard, e.g.
                // "MONITORING", "LOCAL_DSO_SUPPORT", "UPWARD_SERVICE",
                // or "DOWNWARD_SERVICE".
                #measureAttribute decisionMode {
                    :>> dataType default AttributeDataType::STRING;
                }

                // Incremented by the decision federation on every completed
                // decision. It is the reliable trigger for forwarding both EC
                // updates even when one of the numerical power values happens
                // to remain unchanged.
                #measureAttribute decisionVersion {
                    :>> dataType default AttributeDataType::DOUBLE;
                }
            }
        }

        :>> hotDatabaseRetentionDays default 30;
        :>> coldDatabaseRetentionDays default 30;

        // ----------------------------------------------------------------- //
        // Input-reporting conditions. Any relevant state update can re-run the Aggregator federation decision.
        // ----------------------------------------------------------------- //

        #condition tsoReporting : AggregatorTSOInputStrategy {
            :>> leftOperand = dtcAggreg.tsoInput.requestedPower;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcAggreg.tsoInput.requestedPower;
            :>> aggregatorTSOUpdate {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                requestedPower :>> inputParameters = dtcAggreg.tsoInput.requestedPower;
                serviceDirection :>> inputParameters = dtcAggreg.tsoInput.serviceDirection;
            }
        }

        #condition dsoTS1Reporting : AggregatorDSOTS1InputStrategy {
            :>> leftOperand = dtcAggreg.dsoInput.ts1VoltageStatus;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcAggreg.dsoInput.ts1VoltageStatus;
            :>> aggregatorDSOTS1Update {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                ts1VoltageStatus :>> inputParameters = dtcAggreg.dsoInput.ts1VoltageStatus;
                ts1ExchangeLimit :>> inputParameters = dtcAggreg.dsoInput.ts1ExchangeLimit;
            }
        }

        #condition dsoTS2Reporting : AggregatorDSOTS2InputStrategy {
            :>> leftOperand = dtcAggreg.dsoInput.ts2VoltageStatus;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcAggreg.dsoInput.ts2VoltageStatus;
            :>> aggregatorDSOTS2Update {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                ts2ExchangeLimit :>> inputParameters = dtcAggreg.dsoInput.ts2ExchangeLimit;
            }
        }

        #condition ec1BatteryReporting : AggregatorEC1BatteryInputStrategy {
            :>> leftOperand = dtcAggreg.ec1Input.ec1BatteryPower;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcAggreg.ec1Input.ec1BatteryPower;
            :>> aggregatorEC1BatteryUpdate {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                ec1BatteryPower :>> inputParameters = dtcAggreg.ec1Input.ec1BatteryPower;
                ec1BatteryStateOfCharge :>> inputParameters = dtcAggreg.ec1Input.ec1BatteryStateOfCharge;
            }
        }

        #condition ec1PVReporting : AggregatorEC1PVInputStrategy {
            :>> leftOperand = dtcAggreg.ec1Input.ec1PVPower;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcAggreg.ec1Input.ec1PVPower;
            :>> aggregatorEC1PVUpdate {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                ec1PVPower :>> inputParameters = dtcAggreg.ec1Input.ec1PVPower;
            }
        }

        #condition ec1DSRReporting : AggregatorEC1DSRInputStrategy {
            :>> leftOperand = dtcAggreg.ec1Input.ec1DSRPower;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcAggreg.ec1Input.ec1DSRPower;
            :>> aggregatorEC1DSRUpdate {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                ec1DSRPower :>> inputParameters = dtcAggreg.ec1Input.ec1DSRPower;
            }
        }

        #condition ec2BatteryReporting : AggregatorEC2BatteryInputStrategy {
            :>> leftOperand = dtcAggreg.ec2Input.ec2BatteryPower;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcAggreg.ec2Input.ec2BatteryPower;
            :>> aggregatorEC2BatteryUpdate {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                ec2BatteryPower :>> inputParameters = dtcAggreg.ec2Input.ec2BatteryPower;
                ec2BatteryStateOfCharge :>> inputParameters = dtcAggreg.ec2Input.ec2BatteryStateOfCharge;
            }
        }

        #condition ec2PVReporting : AggregatorEC2PVInputStrategy {
            :>> leftOperand = dtcAggreg.ec2Input.ec2PVPower;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcAggreg.ec2Input.ec2PVPower;
            :>> aggregatorEC2PVUpdate {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                ec2PVPower :>> inputParameters = dtcAggreg.ec2Input.ec2PVPower;
            }
        }

        #condition ec2DSRReporting : AggregatorEC2DSRInputStrategy {
            :>> leftOperand = dtcAggreg.ec2Input.ec2DSRPower;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcAggreg.ec2Input.ec2DSRPower;
            :>> aggregatorEC2DSRUpdate {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                ec2DSRPower :>> inputParameters = dtcAggreg.ec2Input.ec2DSRPower;
            }
        }

        // ----------------------------------------------------------------- //
        // Output-reporting conditions. The same decisionVersion update causes
        // all six direct telemetry strategies to run.
        // ----------------------------------------------------------------- //

        #condition ec1BatteryDecisionReporting : AggregatorEC1BatteryDecisionUpdateStrategy {
            :>> leftOperand = dtcAggreg.decision.decisionVersion;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcAggreg.decision.decisionVersion;
            :>> decisionEC1BatteryUpdate {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                ec1BatteryPower :>> inputParameters = dtcAggreg.decision.ec1BatteryPower;
            }
        }

        #condition ec1DSRDecisionReporting : AggregatorEC1DSRDecisionUpdateStrategy {
            :>> leftOperand = dtcAggreg.decision.decisionVersion;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcAggreg.decision.decisionVersion;
            :>> decisionEC1DSRUpdate {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                ec1DSRPower :>> inputParameters = dtcAggreg.decision.ec1DSRPower;
            }
        }

        #condition ec2BatteryDecisionReporting : AggregatorEC2BatteryDecisionUpdateStrategy {
            :>> leftOperand = dtcAggreg.decision.decisionVersion;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcAggreg.decision.decisionVersion;
            :>> decisionEC2BatteryUpdate {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                ec2BatteryPower :>> inputParameters = dtcAggreg.decision.ec2BatteryPower;
            }
        }

        #condition ec2DSRDecisionReporting : AggregatorEC2DSRDecisionUpdateStrategy {
            :>> leftOperand = dtcAggreg.decision.decisionVersion;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcAggreg.decision.decisionVersion;
            :>> decisionEC2DSRUpdate {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                ec2DSRPower :>> inputParameters = dtcAggreg.decision.ec2DSRPower;
            }
        }

        #condition ts1ExchangeDecisionReporting : AggregatorTS1ExchangeDecisionUpdateStrategy {
            :>> leftOperand = dtcAggreg.decision.decisionVersion;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcAggreg.decision.decisionVersion;
            :>> decisionTS1ExchangeUpdate {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                ts1ExchangePower :>> inputParameters = dtcAggreg.decision.ts1ExchangePower;
            }
        }

        #condition ts2ExchangeDecisionReporting : AggregatorTS2ExchangeDecisionUpdateStrategy {
            :>> leftOperand = dtcAggreg.decision.decisionVersion;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcAggreg.decision.decisionVersion;
            :>> decisionTS2ExchangeUpdate {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                ts2ExchangePower :>> inputParameters = dtcAggreg.decision.ts2ExchangePower;
            }
        }
    }
}
