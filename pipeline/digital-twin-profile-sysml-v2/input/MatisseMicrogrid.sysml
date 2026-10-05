package MatisseMicrogrid {

    private import MetaModelDigitalTwin::*;

    // Every PAC device reports consumption.
    #Component def PAC_Sensor {
        #measureAttribute consumption {
            :>> dataType default AttributeDataType::DOUBLE;
        }
    }

    #Entity def Battery {
        #component sensor : PAC_Sensor {
            #measureAttribute totalCapacity {
                :>> dataType default AttributeDataType::INTEGER;
            }
        }
    }

    #Entity def PV {
        #component sensor : PAC_Sensor {
            #measureAttribute output {
                :>> dataType default AttributeDataType::DOUBLE;
            }
        }
    }

    #Condition def StopCharging {
        #strategyAction stopCharging :>> strategieActions {
            :>> name = "stopCharging";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/microgrid/stopCharging";
            :>> external = false;
        }
    }

    #Condition def StopChargingP14 {
        #strategyAction stopChargingP14 :>> strategieActions {
            :>> name = "stopChargingP14";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "/pipeline/code/microgrid/stopCharging";
            :>> external = false;
            :>> feedbackTopicType = FeedbackTopicType::NOFEEDBACK;
        }
    }

    #Entity def Charger {
        // The v1 converter exports this as CONST_PROPERTIES.MaxConsumption.
        #constAttribute maxConsumption {
            :>> value default "4343434";
            :>> dataType default AttributeDataType::INTEGER;
        }
        #component sensor : PAC_Sensor;
    }

    #Twin def MantisseMG {
        #entity MicroGrid {
            #entity battery : Battery {
                p16 :>> sensor;
            }

            #entity KebaP30 : Charger {
                :>> maxConsumption {
                    :>> value default "4343";
                }
                p13 :>> sensor {
                    #measureAttribute power {
                        :>> dataType default AttributeDataType::DOUBLE;
                    }
                }
            }

            // Named "Sie Versicharge" in the v1 hierarchy.
            #entity SieVersicharge : Charger {
                p14 :>> sensor;
            }

            #entity SieChargeCC : Charger {
                p12 :>> sensor;
            }

            #entity pv : PV {
                pV1 :>> sensor;
            }

            #entity SieChargeD : Charger {
                p17 :>> sensor;
            }

            #entity SieCPC20 : Charger {
                p11 :>> sensor;
            }
        }

        :>> hotDatabaseRetentionDays default 30;
        :>> coldDatabaseRetentionDays default 30;

        #condition stopCharging : StopCharging {
            :>> leftOperand = MicroGrid.KebaP30.p13.consumption;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = MicroGrid.KebaP30.maxConsumption;
            :>> stopCharging {
                :>> feedbackTopicType = FeedbackTopicType::INTERN;
                :>> componentTopic = MicroGrid.KebaP30.p13;
            }
        }

        #condition stopChargingP14 : StopChargingP14 {
            :>> leftOperand = MicroGrid.SieVersicharge.p14.consumption;
            :>> operator = ComparisonOperator::EQUAL;
            :>> rightOperand = MicroGrid.SieVersicharge.maxConsumption;
        }
    }
}
