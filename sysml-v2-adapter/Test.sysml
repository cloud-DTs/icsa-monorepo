package MGrid {

    private import MetaModelDigitalTwin::*;

    // ── Def without measurements: every usage adds its own -> each usage gets its own type
    #Component def PAC_Sensor { }

    // ── Def with fixed schema, nothing added in usages -> shared type
    #Component def BatteryController { }

    #Component def ChargerSensor {
        #measureAttribute power {
            :>> dataType default AttributeDataType::DOUBLE;
        }
        #measureAttribute consumption {
            :>> dataType default AttributeDataType::DOUBLE;
        }
    }

    // ── Def hierarchy: BaseMeter <- EnergyMeter <- SmartMeter
    #Component def BaseMeter {
        #measureAttribute power {
            :>> dataType default AttributeDataType::DOUBLE;
        }
    }
    #Component def EnergyMeter :> BaseMeter {
        #measureAttribute energy {
            :>> dataType default AttributeDataType::DOUBLE;
        }
    }
    #Component def Test{

    }
    #Component def SmartMeter :> EnergyMeter {
        #measureAttribute voltage {
            :>> dataType default AttributeDataType::DOUBLE;
        }
    }

    #Entity def Battery {
        #component sensor : PAC_Sensor {
            #measureAttribute totalCapacity {
                :>> dataType default AttributeDataType::INTEGER;
            }
            #measureAttribute power {
                :>> dataType default AttributeDataType::DOUBLE;
            }
        }
        #component controller : BatteryController;
    }

    #Entity def PV {
        #component sensor : PAC_Sensor {
            #measureAttribute output {
                :>> dataType default AttributeDataType::DOUBLE;
            }
        }
    }

    #Entity def Charger {
        #constAttribute maxConsumption {
            :>> value default "50.0";
            :>> dataType default AttributeDataType::DOUBLE;
        }
        #component sensor : ChargerSensor;
    }

    #Entity def Household {
        #component meter : SmartMeter;
    }

    #Condition def ChargerChanged {
        #strategyAction balance :>> strategieActions {
            :>> name = "Balance";
            :>> strategyType = StrategyType::LAMBDA;
            :>> pathToCode = "lambda_functions/event_actions/energy-management";
            :>> external = false;
            :>> feedbackTopicType = FeedbackTopicType::INTERN;
        }
    }

    #Twin def MGrid {
        #entity MicroGrid {
            #constAttribute chargingThreshold {
                :>> value default "0.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }

            #entity battery : Battery { p16 :>> sensor; }
            #entity pv : PV { pV1 :>> sensor; }

            // expected: all 5 chargers share type ChargerSensor
            #entity charger1 : Charger {
                :>> maxConsumption { :>> value default "15.0"; }
                p13 :>> sensor;
            }
            #entity charger2 : Charger { p14 :>> sensor; }
            #entity charger3 : Charger { p12 :>> sensor; }
            #entity charger4 : Charger { p17 :>> sensor; }

            // expected: own type (adds attribute in usage)
            #entity charger5 : Charger {
                p11 :>> sensor {
                    #measureAttribute temperature {
                        :>> dataType default AttributeDataType::DOUBLE;
                    }
                }
            }

            // ── nested entities, def hierarchy
            #entity district {
                // expected: shared type SmartMeter (inherited power + energy + voltage)
                #entity house1 : Household;
                #entity house2 : Household;

                // expected: own type (adds attribute)
                #entity house3 : Household {
                    :>> meter {
                        #measureAttribute frequency {
                            :>> dataType default AttributeDataType::DOUBLE;
                        }
                    }
                }

                // expected: own type (redefines dataType of inherited power)
                #entity house4 : Household {
                    :>> meter {
                        :>> power { :>> dataType default AttributeDataType::INTEGER; }
                    }
                }

                // expected: shared type EnergyMeter (direct usage of mid-level def)
                #entity street {
                    #component em1 : EnergyMeter;
                    #component em2 : EnergyMeter;
                }

                // expected: shared type BaseMeter
                #entity garage {
                    #component bm1 : BaseMeter;
                }
            }

            // ── components without explicit def -> own type each, even with same schema
            #entity weatherStation {
                #component tempSensor {
                    #measureAttribute temperature {
                        :>> dataType default AttributeDataType::DOUBLE;
                    }
                }
                #component tempSensor2 {
                    #measureAttribute temperature {
                        :>> dataType default AttributeDataType::DOUBLE;
                    }
                }
                // here the will take the library definiton of Component
                 #component tempSensor3 {

                                }
                                //same as tempsensor3
                 #component tempSensor4 {

                                                 }
                #component windSensor {
                    #measureAttribute speed {
                        :>> dataType default AttributeDataType::DOUBLE;
                    }
                    #measureAttribute direction {
                        :>> dataType default AttributeDataType::STRING;
                    }
                }
            }
        }

        :>> hotDatabaseRetentionDays default 30;
        :>> coldDatabaseRetentionDays default 30;

        #condition charger1Changed : ChargerChanged {
            :>> leftOperand = MicroGrid.charger1.p13.power;
            :>> operator = ComparisonOperator::GREATER_THAN;
            :>> rightOperand = MicroGrid.chargingThreshold;
        }
        #condition charger2Changed : ChargerChanged {
            :>> leftOperand = MicroGrid.charger2.p14.power;
            :>> operator = ComparisonOperator::GREATER_THAN;
            :>> rightOperand = MicroGrid.chargingThreshold;
            balance2 :>> balance {
                :>> componentTopic = MicroGrid.battery.controller;
            }
        }
        #condition charger3Changed : ChargerChanged {
            :>> leftOperand = MicroGrid.charger3.p12.power;
            :>> operator = ComparisonOperator::GREATER_THAN;
            :>> rightOperand = MicroGrid.chargingThreshold;
            balance3 :>> balance {
                :>> componentTopic = MicroGrid.battery.controller;
            }
        }
        #condition charger4Changed : ChargerChanged {
            :>> leftOperand = MicroGrid.charger4.p17.power;
            :>> operator = ComparisonOperator::GREATER_THAN;
            :>> rightOperand = MicroGrid.chargingThreshold;
            balance4 :>> balance {
                :>> componentTopic = MicroGrid.battery.controller;
            }
        }
        #condition charger5Changed : ChargerChanged {
            :>> leftOperand = MicroGrid.charger5.p11.power;
            :>> operator = ComparisonOperator::GREATER_THAN;
            :>> rightOperand = MicroGrid.chargingThreshold;
            balance5 :>> balance {
                :>> componentTopic = MicroGrid.battery.controller;
            }
        }
    }
}
