package dtc2pv {
    private import MetaModelDigitalTwin::*;

    #Component def PV_Sensor { }

    #Condition def PVProductionStrategy {
        #strategyAction production :>> strategieActions {
            :>> name = "production";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/microgrid/pv/production";
            :>> external = false;
        }
    }

    #Twin def dtc2pv {
        #entity dtc2pv {
            #component sensor : PV_Sensor {
                #measureAttribute generatedPower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }
            }
        }
        

        :>> hotDatabaseRetentionDays default 30;
        :>> coldDatabaseRetentionDays default 30;

        #condition isGenerating : PVProductionStrategy {
            :>> leftOperand = dtc2pv.sensor.generatedPower;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtc2pv.sensor.generatedPower;
            :>> production {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                generatedPower :>> inputParameters = dtc2pv.sensor.generatedPower;
            }
        }
    }
}
