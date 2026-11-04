package dtcEC1 {
    private import MetaModelDigitalTwin::*;

    #Component def EC1Battery_Sensor { }
    #Component def EC1PV_Sensor { }
    #Component def EC1DSR_Sensor { }

    #Condition def EC1BatteryUpdateStrategy {
        #strategyAction batteryUpdate :>> strategieActions {
            :>> name = "batteryUpdate";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/meps-demo/trigger";
            :>> external = false;
        }
    }

    #Condition def EC1PVUpdateStrategy {
        #strategyAction pvUpdate :>> strategieActions {
            :>> name = "pvUpdate";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/meps-demo/trigger";
            :>> external = false;
        }
    }

    #Condition def EC1DSRUpdateStrategy {
        #strategyAction dsrUpdate :>> strategieActions {
            :>> name = "dsrUpdate";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/meps-demo/trigger";
            :>> external = false;
        }
    }

    #Twin def dtcEC1 {
        #entity dtcEC1 {
            #component battery : EC1Battery_Sensor {
                #measureAttribute stateOfCharge {
                    :>> dataType default AttributeDataType::DOUBLE;
                }

                // Positive = charging/absorption; negative = discharging/upward flexibility.
                #measureAttribute batteryPower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }
            }

            #component pv : EC1PV_Sensor {
                #measureAttribute pvPower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }
            }

            #component dsr : EC1DSR_Sensor {
                // Positive = increased demand; negative = reduced demand/upward flexibility.
                #measureAttribute dsrPower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }
            }

            #constAttribute substationId {
                :>> value default "TS1";
                :>> dataType default AttributeDataType::STRING;
            }

            #constAttribute maxBatteryChargingPower {
                :>> value default "10.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }

            #constAttribute maxBatteryDischargingPower {
                :>> value default "10.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }

            #constAttribute maxDSRFlexibility {
                :>> value default "3.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
        }

        :>> hotDatabaseRetentionDays default 30;
        :>> coldDatabaseRetentionDays default 30;

        #condition batteryReporting : EC1BatteryUpdateStrategy {
            :>> leftOperand = dtcEC1.battery.batteryPower;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcEC1.battery.batteryPower;
            :>> batteryUpdate {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                batteryPower :>> inputParameters = dtcEC1.battery.batteryPower;
                stateOfCharge :>> inputParameters = dtcEC1.battery.stateOfCharge;
            }
        }

        #condition pvReporting : EC1PVUpdateStrategy {
            :>> leftOperand = dtcEC1.pv.pvPower;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcEC1.pv.pvPower;
            :>> pvUpdate {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                pvPower :>> inputParameters = dtcEC1.pv.pvPower;
            }
        }

        #condition dsrReporting : EC1DSRUpdateStrategy {
            :>> leftOperand = dtcEC1.dsr.dsrPower;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcEC1.dsr.dsrPower;
            :>> dsrUpdate {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                dsrPower :>> inputParameters = dtcEC1.dsr.dsrPower;
            }
        }
    }
}
