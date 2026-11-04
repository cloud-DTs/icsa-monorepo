package dtcEC2 {
    private import MetaModelDigitalTwin::*;

    #Component def EC2Battery_Sensor { }
    #Component def EC2PV_Sensor { }
    #Component def EC2DSR_Sensor { }

    #Condition def EC2BatteryUpdateStrategy {
        #strategyAction ec2BatteryUpdate :>> strategieActions {
            :>> name = "ec2BatteryUpdate";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/meps-demo/trigger";
            :>> external = false;
        }
    }

    #Condition def EC2PVUpdateStrategy {
        #strategyAction ec2PVUpdate :>> strategieActions {
            :>> name = "ec2PVUpdate";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/meps-demo/trigger";
            :>> external = false;
        }
    }

    #Condition def EC2DSRUpdateStrategy {
        #strategyAction ec2DSRUpdate :>> strategieActions {
            :>> name = "ec2DSRUpdate";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/meps-demo/trigger";
            :>> external = false;
        }
    }

    #Twin def dtcEC2 {
        #entity dtcEC2 {
            #component battery : EC2Battery_Sensor {
                #measureAttribute stateOfCharge {
                    :>> dataType default AttributeDataType::DOUBLE;
                }

                // Positive = charging/absorption; negative = discharging/upward flexibility.
                #measureAttribute batteryPower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }
            }

            #component pv : EC2PV_Sensor {
                #measureAttribute pvPower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }
            }

            #component dsr : EC2DSR_Sensor {
                // Positive = increased demand; negative = reduced demand/upward flexibility.
                #measureAttribute dsrPower {
                    :>> dataType default AttributeDataType::DOUBLE;
                }
            }

            #constAttribute substationId {
                :>> value default "TS2";
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

        #condition batteryReporting : EC2BatteryUpdateStrategy {
            :>> leftOperand = dtcEC2.battery.batteryPower;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcEC2.battery.batteryPower;
            :>> ec2BatteryUpdate {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                batteryPower :>> inputParameters = dtcEC2.battery.batteryPower;
                stateOfCharge :>> inputParameters = dtcEC2.battery.stateOfCharge;
            }
        }

        #condition pvReporting : EC2PVUpdateStrategy {
            :>> leftOperand = dtcEC2.pv.pvPower;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcEC2.pv.pvPower;
            :>> ec2PVUpdate {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                pvPower :>> inputParameters = dtcEC2.pv.pvPower;
            }
        }

        #condition dsrReporting : EC2DSRUpdateStrategy {
            :>> leftOperand = dtcEC2.dsr.dsrPower;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = dtcEC2.dsr.dsrPower;
            :>> ec2DSRUpdate {
                :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
                dsrPower :>> inputParameters = dtcEC2.dsr.dsrPower;
            }
        }
    }
}
