package dtc2bat {

    private import MetaModelDigitalTwin::*;

    #Component def PAC_Sensor { }

    #Component def PV_Virtual_Sensor { }


    #Condition def BatteryStatusStrategy {
        #strategyAction status :>> strategieActions {
            :>> name = "status";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/microgrid/battery/status";
            :>> external = false;
        }
    }

    #Twin def dtc2bat {
        #entity dtc2bat {
            #component p16 : PAC_Sensor {
                #measureAttribute isPlugged {
                    :>> dataType default AttributeDataType::STRING;
                }
                #measureAttribute charges {
                    :>> dataType default AttributeDataType::INTEGER;
                }
                #measureAttribute consumption {
                    :>> dataType default AttributeDataType::DOUBLE;
                }
            }
            #component pvInput : PV_Virtual_Sensor {
                #measureAttribute pvGeneratedPower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }
            }
            #constAttribute trueValue {
                :>> value default "true";
                :>> dataType default AttributeDataType::STRING;
            }
            #constAttribute maxTemp {
                :>> value default "50.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
        }

        :>> hotDatabaseRetentionDays default 30;
        :>> coldDatabaseRetentionDays default 30;

        #condition operational : BatteryStatusStrategy {
            :>> leftOperand = dtc2bat.p16.isPlugged;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtc2bat.trueValue;
            :>> status {
                :>> feedbackTopicType = FeedbackTopicType::EXTERN;
                chargeValue :>> inputParameters = dtc2bat.p16.charges;
                :>> externalTopic = "dtc2bat/iot-data";
            }
        }
    }
}
