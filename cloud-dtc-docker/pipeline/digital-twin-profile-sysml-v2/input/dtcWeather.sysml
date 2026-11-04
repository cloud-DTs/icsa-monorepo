package dtcWeather {
    private import MetaModelDigitalTwin::*;

    #Component def WeatherForecast_Sensor { }

    #Twin def dtcWeather {
        #entity dtcWeather {
            // Empty sensor component retained for structure. The forecast data
            // below is declared at #entity level (NOT inside this component)
            // because the converter drops #constAttribute nested in a component;
            // entity-level consts materialize as a generated const_component
            // (named dtcWeatherconst_component), which is what the hot-reader
            // queries.
            #component forecast : WeatherForecast_Sensor { }

            // Hardcoded hourly solar availability forecast (0-100%) for a sunny
            // summer day in Innsbruck, Austria. Fixed lookup table only - no
            // Lambda/condition/strategy and no reference to any other twin.
            #constAttribute hour00 {
                :>> value default "0.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute hour01 {
                :>> value default "0.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute hour02 {
                :>> value default "0.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute hour03 {
                :>> value default "0.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute hour04 {
                :>> value default "0.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute hour05 {
                :>> value default "0.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute hour06 {
                :>> value default "0.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute hour07 {
                :>> value default "5.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute hour08 {
                :>> value default "20.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute hour09 {
                :>> value default "40.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute hour10 {
                :>> value default "60.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute hour11 {
                :>> value default "80.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute hour12 {
                :>> value default "100.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute hour13 {
                :>> value default "100.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute hour14 {
                :>> value default "85.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute hour15 {
                :>> value default "70.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute hour16 {
                :>> value default "50.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute hour17 {
                :>> value default "35.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute hour18 {
                :>> value default "20.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute hour19 {
                :>> value default "8.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute hour20 {
                :>> value default "0.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute hour21 {
                :>> value default "0.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute hour22 {
                :>> value default "0.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
            #constAttribute hour23 {
                :>> value default "0.0";
                :>> dataType default AttributeDataType::DOUBLE;
            }
        }

        :>> hotDatabaseRetentionDays default 30;
        :>> coldDatabaseRetentionDays default 30;
    }
}
