package CoffeeMachineTwinModel {

    private import MetaModelDigitalTwin::*;

    // Sensor component types
    #Component def TemperatureSensor {
        #measureAttribute temperatureC {
            :>> dataType default AttributeDataType::DOUBLE;
        }
    }

    #Component def PercentLevelSensor {
        #measureAttribute levelPercent {
            :>> dataType default AttributeDataType::DOUBLE;
        }
    }

    #Component def FlowMeterSensor {
        #measureAttribute flowRateMlPerSecond {
            :>> dataType default AttributeDataType::DOUBLE;
        }
        #measureAttribute totalVolumeMl {
            :>> dataType default AttributeDataType::DOUBLE;
        }
    }

    #Component def PressureSensor {
        #measureAttribute pressureBar {
            :>> dataType default AttributeDataType::DOUBLE;
        }
    }

    #Component def RotationSensor {
        #measureAttribute speedRpm {
            :>> dataType default AttributeDataType::INTEGER;
        }
    }

    #Component def PresenceSensor {
        #measureAttribute present {
            :>> dataType default AttributeDataType::INTEGER;
        }
    }

    #Component def InterlockSensor {
        #measureAttribute closed {
            :>> dataType default AttributeDataType::INTEGER;
        }
    }

    // Actuator component types. Their measured attributes report the applied state.
    #Component def HeaterActuator {
        #measureAttribute enabled {
            :>> dataType default AttributeDataType::INTEGER;
        }
        #measureAttribute dutyCyclePercent {
            :>> dataType default AttributeDataType::DOUBLE;
        }
    }

    #Component def PumpActuator {
        #measureAttribute enabled {
            :>> dataType default AttributeDataType::INTEGER;
        }
        #measureAttribute targetPressureBar {
            :>> dataType default AttributeDataType::DOUBLE;
        }
    }

    #Component def GrinderActuator {
        #measureAttribute enabled {
            :>> dataType default AttributeDataType::INTEGER;
        }
        #measureAttribute targetDoseGrams {
            :>> dataType default AttributeDataType::DOUBLE;
        }
    }

    #Component def ValveActuator {
        #measureAttribute open {
            :>> dataType default AttributeDataType::INTEGER;
        }
    }

    #Twin def CoffeeTwin {
        #entity coffeeMachine {
            // Static identity and operating envelope
            #constAttribute modelNumber {
                :>> value default "CM-PRO-2G";
                :>> dataType default AttributeDataType::STRING;
            }
            #constAttribute ratedPowerWatts {
                :>> value default "2300";
                :>> dataType default AttributeDataType::INTEGER;
            }
            #constAttribute waterTankCapacityMl {
                :>> value default "2500";
                :>> dataType default AttributeDataType::INTEGER;
            }
            #constAttribute beanHopperCapacityGrams {
                :>> value default "500";
                :>> dataType default AttributeDataType::INTEGER;
            }

            // Control thresholds
            #constAttribute maximumBoilerTemperatureC {
                :>> value default "96.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute minimumGroupHeadTemperatureC {
                :>> value default "88.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute minimumWaterLevelPercent {
                :>> value default "10.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute targetShotVolumeMl {
                :>> value default "36.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute maximumBrewPressureBar {
                :>> value default "10.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute minimumBeanLevelPercent {
                :>> value default "5.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute minimumGrinderSpeedRpm {
                :>> value default "500";
                :>> dataType default AttributeDataType::INTEGER;
            }
            #constAttribute maximumDripTrayLevelPercent {
                :>> value default "85.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute requiredPresenceState {
                :>> value default "1";
                :>> dataType default AttributeDataType::INTEGER;
            }
            #constAttribute requiredDoorClosedState {
                :>> value default "1";
                :>> dataType default AttributeDataType::INTEGER;
            }

            // Ten independently addressable sensor endpoints
            #entity sensors {
                #component brewBoilerTemperature : TemperatureSensor;
                #component groupHeadTemperature : TemperatureSensor;
                #component waterTankLevel : PercentLevelSensor;
                #component brewFlow : FlowMeterSensor;
                #component brewPressure : PressureSensor;
                #component beanHopperLevel : PercentLevelSensor;
                #component grinderSpeed : RotationSensor;
                #component dripTrayLevel : PercentLevelSensor;
                #component cupPresence : PresenceSensor;
                #component serviceDoor : InterlockSensor;
            }

            // Four independently commandable actuator endpoints
            #entity actuators {
                #component heater : HeaterActuator;
                #component waterPump : PumpActuator;
                #component grinderMotor : GrinderActuator;
                #component brewValve : ValveActuator;
            }
        }

        :>> hotDatabaseType default LibTwinDataBaseType::TIMESERIES;
        :>> hotDatabaseRetentionDays default 30;
        :>> coldDataBaseType default LibTwinDataBaseType::RELATIONAL;
        :>> coldDatabaseRetentionDays default 365;

        #condition boilerOverTemperature {
            :>> leftOperand = coffeeMachine.sensors.brewBoilerTemperature.temperatureC;
            :>> operator = ComparisonOperator::GREATER_THAN;
            :>> rightOperand = coffeeMachine.maximumBoilerTemperatureC;

            #strategyAction disableHeater :>> strategieActions {
                :>> name = "disableHeater";
                :>> strategyType = StrategyType::LAMBDA;
                :>> pathToCode = "/pipeline/code/coffee-machine/set-heater";
                :>> external = false;
                measuredTemperature :>> inputParameters = coffeeMachine.sensors.brewBoilerTemperature.temperatureC;
                allowedTemperature :>> inputParameters = coffeeMachine.maximumBoilerTemperatureC;
                command :>> outputParameters = AttributeDataType::STRING;
                reason :>> outputParameters = AttributeDataType::STRING;
                :>> feedbackTopicType = FeedbackTopicType::INTERN;
                :>> componentTopic = coffeeMachine.actuators.heater;
            }
        }

        #condition groupHeadNeedsWarmup {
            :>> leftOperand = coffeeMachine.sensors.groupHeadTemperature.temperatureC;
            :>> operator = ComparisonOperator::LESS_THAN;
            :>> rightOperand = coffeeMachine.minimumGroupHeadTemperatureC;

            #strategyAction enableHeater :>> strategieActions {
                :>> name = "enableHeater";
                :>> strategyType = StrategyType::LAMBDA;
                :>> pathToCode = "/pipeline/code/coffee-machine/set-heater";
                :>> external = false;
                measuredTemperature :>> inputParameters = coffeeMachine.sensors.groupHeadTemperature.temperatureC;
                requiredTemperature :>> inputParameters = coffeeMachine.minimumGroupHeadTemperatureC;
                command :>> outputParameters = AttributeDataType::STRING;
                reason :>> outputParameters = AttributeDataType::STRING;
                :>> feedbackTopicType = FeedbackTopicType::INTERN;
                :>> componentTopic = coffeeMachine.actuators.heater;
            }
        }

        #condition waterSupplyLow {
            :>> leftOperand = coffeeMachine.sensors.waterTankLevel.levelPercent;
            :>> operator = ComparisonOperator::LESS_THAN;
            :>> rightOperand = coffeeMachine.minimumWaterLevelPercent;

            #strategyAction stopPumpForLowWater :>> strategieActions {
                :>> name = "stopPumpForLowWater";
                :>> strategyType = StrategyType::LAMBDA;
                :>> pathToCode = "/pipeline/code/coffee-machine/stop-pump";
                :>> external = false;
                measuredLevel :>> inputParameters = coffeeMachine.sensors.waterTankLevel.levelPercent;
                minimumLevel :>> inputParameters = coffeeMachine.minimumWaterLevelPercent;
                command :>> outputParameters = AttributeDataType::STRING;
                reason :>> outputParameters = AttributeDataType::STRING;
                :>> feedbackTopicType = FeedbackTopicType::INTERN;
                :>> componentTopic = coffeeMachine.actuators.waterPump;
            }
        }

        #condition targetShotVolumeReached {
            :>> leftOperand = coffeeMachine.sensors.brewFlow.totalVolumeMl;
            :>> operator = ComparisonOperator::GREATER_THAN;
            :>> rightOperand = coffeeMachine.targetShotVolumeMl;

            #strategyAction closeValveAtTargetVolume :>> strategieActions {
                :>> name = "closeValveAtTargetVolume";
                :>> strategyType = StrategyType::LAMBDA;
                :>> pathToCode = "/pipeline/code/coffee-machine/close-brew-valve";
                :>> external = false;
                measuredVolume :>> inputParameters = coffeeMachine.sensors.brewFlow.totalVolumeMl;
                targetVolume :>> inputParameters = coffeeMachine.targetShotVolumeMl;
                currentFlowRate :>> inputParameters = coffeeMachine.sensors.brewFlow.flowRateMlPerSecond;
                command :>> outputParameters = AttributeDataType::STRING;
                reason :>> outputParameters = AttributeDataType::STRING;
                :>> feedbackTopicType = FeedbackTopicType::INTERN;
                :>> componentTopic = coffeeMachine.actuators.brewValve;
            }
        }

        #condition brewPressureTooHigh {
            :>> leftOperand = coffeeMachine.sensors.brewPressure.pressureBar;
            :>> operator = ComparisonOperator::GREATER_THAN;
            :>> rightOperand = coffeeMachine.maximumBrewPressureBar;

            #strategyAction stopPumpForHighPressure :>> strategieActions {
                :>> name = "stopPumpForHighPressure";
                :>> strategyType = StrategyType::LAMBDA;
                :>> pathToCode = "/pipeline/code/coffee-machine/stop-pump";
                :>> external = false;
                measuredPressure :>> inputParameters = coffeeMachine.sensors.brewPressure.pressureBar;
                maximumPressure :>> inputParameters = coffeeMachine.maximumBrewPressureBar;
                command :>> outputParameters = AttributeDataType::STRING;
                reason :>> outputParameters = AttributeDataType::STRING;
                :>> feedbackTopicType = FeedbackTopicType::INTERN;
                :>> componentTopic = coffeeMachine.actuators.waterPump;
            }

            #strategyAction closeValveForHighPressure :>> strategieActions {
                :>> name = "closeValveForHighPressure";
                :>> strategyType = StrategyType::LAMBDA;
                :>> pathToCode = "/pipeline/code/coffee-machine/close-brew-valve";
                :>> external = false;
                measuredPressure :>> inputParameters = coffeeMachine.sensors.brewPressure.pressureBar;
                maximumPressure :>> inputParameters = coffeeMachine.maximumBrewPressureBar;
                command :>> outputParameters = AttributeDataType::STRING;
                reason :>> outputParameters = AttributeDataType::STRING;
                :>> feedbackTopicType = FeedbackTopicType::INTERN;
                :>> componentTopic = coffeeMachine.actuators.brewValve;
            }
        }

        #condition beanHopperLow {
            :>> leftOperand = coffeeMachine.sensors.beanHopperLevel.levelPercent;
            :>> operator = ComparisonOperator::LESS_THAN;
            :>> rightOperand = coffeeMachine.minimumBeanLevelPercent;

            #strategyAction stopGrinderForLowBeans :>> strategieActions {
                :>> name = "stopGrinderForLowBeans";
                :>> strategyType = StrategyType::LAMBDA;
                :>> pathToCode = "/pipeline/code/coffee-machine/stop-grinder";
                :>> external = false;
                measuredLevel :>> inputParameters = coffeeMachine.sensors.beanHopperLevel.levelPercent;
                minimumLevel :>> inputParameters = coffeeMachine.minimumBeanLevelPercent;
                command :>> outputParameters = AttributeDataType::STRING;
                reason :>> outputParameters = AttributeDataType::STRING;
                :>> feedbackTopicType = FeedbackTopicType::INTERN;
                :>> componentTopic = coffeeMachine.actuators.grinderMotor;
            }
        }

        #condition grinderSpeedTooLow {
            :>> leftOperand = coffeeMachine.sensors.grinderSpeed.speedRpm;
            :>> operator = ComparisonOperator::LESS_THAN;
            :>> rightOperand = coffeeMachine.minimumGrinderSpeedRpm;

            #strategyAction stopStalledGrinder :>> strategieActions {
                :>> name = "stopStalledGrinder";
                :>> strategyType = StrategyType::LAMBDA;
                :>> pathToCode = "/pipeline/code/coffee-machine/stop-grinder";
                :>> external = false;
                measuredSpeed :>> inputParameters = coffeeMachine.sensors.grinderSpeed.speedRpm;
                minimumSpeed :>> inputParameters = coffeeMachine.minimumGrinderSpeedRpm;
                command :>> outputParameters = AttributeDataType::STRING;
                reason :>> outputParameters = AttributeDataType::STRING;
                :>> feedbackTopicType = FeedbackTopicType::INTERN;
                :>> componentTopic = coffeeMachine.actuators.grinderMotor;
            }
        }

        #condition dripTrayFull {
            :>> leftOperand = coffeeMachine.sensors.dripTrayLevel.levelPercent;
            :>> operator = ComparisonOperator::GREATER_THAN;
            :>> rightOperand = coffeeMachine.maximumDripTrayLevelPercent;

            #strategyAction stopPumpForFullTray :>> strategieActions {
                :>> name = "stopPumpForFullTray";
                :>> strategyType = StrategyType::LAMBDA;
                :>> pathToCode = "/pipeline/code/coffee-machine/stop-pump";
                :>> external = false;
                measuredLevel :>> inputParameters = coffeeMachine.sensors.dripTrayLevel.levelPercent;
                maximumLevel :>> inputParameters = coffeeMachine.maximumDripTrayLevelPercent;
                command :>> outputParameters = AttributeDataType::STRING;
                reason :>> outputParameters = AttributeDataType::STRING;
                :>> feedbackTopicType = FeedbackTopicType::INTERN;
                :>> componentTopic = coffeeMachine.actuators.waterPump;
            }

            #strategyAction closeValveForFullTray :>> strategieActions {
                :>> name = "closeValveForFullTray";
                :>> strategyType = StrategyType::LAMBDA;
                :>> pathToCode = "/pipeline/code/coffee-machine/close-brew-valve";
                :>> external = false;
                measuredLevel :>> inputParameters = coffeeMachine.sensors.dripTrayLevel.levelPercent;
                maximumLevel :>> inputParameters = coffeeMachine.maximumDripTrayLevelPercent;
                command :>> outputParameters = AttributeDataType::STRING;
                reason :>> outputParameters = AttributeDataType::STRING;
                :>> feedbackTopicType = FeedbackTopicType::INTERN;
                :>> componentTopic = coffeeMachine.actuators.brewValve;
            }
        }

        #condition cupMissing {
            :>> leftOperand = coffeeMachine.sensors.cupPresence.present;
            :>> operator = ComparisonOperator::LESS_THAN;
            :>> rightOperand = coffeeMachine.requiredPresenceState;

            #strategyAction closeValveWithoutCup :>> strategieActions {
                :>> name = "closeValveWithoutCup";
                :>> strategyType = StrategyType::LAMBDA;
                :>> pathToCode = "/pipeline/code/coffee-machine/close-brew-valve";
                :>> external = false;
                presenceState :>> inputParameters = coffeeMachine.sensors.cupPresence.present;
                requiredState :>> inputParameters = coffeeMachine.requiredPresenceState;
                command :>> outputParameters = AttributeDataType::STRING;
                reason :>> outputParameters = AttributeDataType::STRING;
                :>> feedbackTopicType = FeedbackTopicType::INTERN;
                :>> componentTopic = coffeeMachine.actuators.brewValve;
            }
        }

        #condition serviceDoorOpen {
            :>> leftOperand = coffeeMachine.sensors.serviceDoor.closed;
            :>> operator = ComparisonOperator::LESS_THAN;
            :>> rightOperand = coffeeMachine.requiredDoorClosedState;

            #strategyAction stopGrinderForOpenDoor :>> strategieActions {
                :>> name = "stopGrinderForOpenDoor";
                :>> strategyType = StrategyType::LAMBDA;
                :>> pathToCode = "/pipeline/code/coffee-machine/stop-grinder";
                :>> external = false;
                doorState :>> inputParameters = coffeeMachine.sensors.serviceDoor.closed;
                requiredState :>> inputParameters = coffeeMachine.requiredDoorClosedState;
                command :>> outputParameters = AttributeDataType::STRING;
                reason :>> outputParameters = AttributeDataType::STRING;
                :>> feedbackTopicType = FeedbackTopicType::INTERN;
                :>> componentTopic = coffeeMachine.actuators.grinderMotor;
            }
        }
    }
}
