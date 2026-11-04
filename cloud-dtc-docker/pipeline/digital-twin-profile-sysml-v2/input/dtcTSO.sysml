package dtcTSO {
    private import MetaModelDigitalTwin::*;

    #Component def TSOServiceRequest_Component { }

    // Trigger-only strategy for a new MEPSO system-service request.
    // The TSO twin exposes the request; portfolio dispatch is calculated by the Aggregator federation strategy.
    #Condition def TSOServiceRequestUpdateStrategy {
        #strategyAction tsoServiceRequestUpdate :>> strategieActions {
            :>> name = "tsoServiceRequestUpdate";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/meps-demo/trigger";
            :>> external = false;
        }
    }

    #Twin def dtcTSO {
        #entity dtcTSO {
            #component serviceRequest : TSOServiceRequest_Component {
                // Requested balancing/flexibility magnitude in MW.
                // The value is non-negative; the direction is carried separately
                // by serviceDirection.
                //
                // MEPSO demo examples:
                //   00:00 -> 0 MW
                //   06:00 -> 12 MW, UPWARD
                //   12:00 -> 10 MW, DOWNWARD
                #measureAttribute requestedPower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }

                // "NONE", "UPWARD", or "DOWNWARD".
                #measureAttribute serviceDirection {
                    :>> dataType default AttributeDataType::STRING;
                }

                // Requested system-service type, e.g. "aFRR" or "mFRR".
                // The current MEPSO scenarios do not distinguish between the two, but the presentation explicitly exposes aFRR / mFRR.
                #measureAttribute serviceType {
                    :>> dataType default AttributeDataType::STRING;
                }
            }
        }

        :>> hotDatabaseRetentionDays default 30;
        :>> coldDatabaseRetentionDays default 30;

        // requestedPower is the event trigger for a new service request. serviceDirection and serviceType are collected with it so the Aggregator receives the complete TSO request in one federation input.
        #condition serviceRequestReporting : TSOServiceRequestUpdateStrategy {
            :>> leftOperand = dtcTSO.serviceRequest.requestedPower;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcTSO.serviceRequest.requestedPower;
            :>> tsoServiceRequestUpdate {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                requestedPower :>> inputParameters = dtcTSO.serviceRequest.requestedPower;
                serviceDirection :>> inputParameters = dtcTSO.serviceRequest.serviceDirection;
                serviceType :>> inputParameters = dtcTSO.serviceRequest.serviceType;
            }
        }
    }
}
