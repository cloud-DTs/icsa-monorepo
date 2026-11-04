package PVTwin {
    private import MetaModelDigitalTwin::*;

    #Component def PV_Sensor { }

    #Condition def PVProductionStrategy {
        #strategyAction production :>> strategieActions {
            :>> name = "production";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/mnt/c/Users/Marco/FedSysML/input/sysml/testLambdaFunctions/pv/production";
            :>> external = false;
        }
    }

    #Twin def PV {
        #entity PV {
            #constAttribute generatedPower {
                :>> value default "50.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
        }
        
        :>> hotDatabaseRetentionDays default 30;
        :>> coldDatabaseRetentionDays default 30;

        #condition isGenerating : PVProductionStrategy {
            :>> leftOperand = PV.generatedPower;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = PV.generatedPower;
            :>> production {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                generatedPower :>>inputParameters = PV.generatedPower;
            }
        }
    }
}