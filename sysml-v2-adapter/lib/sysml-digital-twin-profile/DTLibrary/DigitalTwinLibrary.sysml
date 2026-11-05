library package DigitalTwinLibrary{

    // common base of all enums, maps them to EnumDefinition
    abstract attribute def TwinEnum;

    abstract part libTwinEntities:LibTwinEntity[0..*];

    abstract attribute libTwinDataBaseType:LibTwinDataBaseType;
    abstract attribute retentionDays:ScalarValues::Integer;
    abstract part def LibTwin{
        abstract part redefines libTwinEntities[0..*];
        abstract attribute hotDatabaseType[0..1] redefines libTwinDataBaseType;
        abstract attribute hotDatabaseRetentionDays redefines retentionDays;
        abstract attribute coldDataBaseType[0..1] redefines libTwinDataBaseType;
        abstract attribute coldDatabaseRetentionDays redefines retentionDays;

    }
    abstract attribute const_attributes:ConstAttributes[0..*];
    abstract part sbEntities:LibTwinEntity[0..*];
    abstract part cmponents:LibTwinComponent[0..*];
    abstract action strategies:LibTwinConditionAction[0..*];

    abstract part def LibTwinEntity{
        abstract attribute redefines const_attributes[0..*];
        abstract part redefines sbEntities[0..*];
        abstract part redefines cmponents[0..*];
        abstract action redefines strategies[0..*];


    }
    abstract attribute measurements:LibDTAttributes[0..*];
    abstract part def LibTwinComponent{
        abstract attribute redefines measurements[0..*];
    }


    abstract attribute leftOperand:LibDTAttributes;
    abstract attribute operator:ComparisonOperator;
    abstract attribute rightOperand:LibDTAttributes;
    abstract part strategieActions:LibTwinStrategyAction[0..*];


    abstract action def LibTwinConditionAction{
        abstract attribute redefines leftOperand[0..1];
        abstract attribute redefines operator[0..1];
        abstract attribute redefines rightOperand[0..1];
        abstract part redefines strategieActions[0..*];
    }
    abstract attribute name:ScalarValues::String;
    abstract attribute description:ScalarValues::String;
    abstract attribute pathToCode:ScalarValues::String;
    abstract attribute external:ScalarValues::Boolean;
    abstract attribute strategyType:StrategyType;

    abstract attribute customPayload:ScalarValues::String;
    abstract part componentTopic:LibTwinComponent;
    abstract attribute externalTopic:ScalarValues::String;
    abstract attribute useExternalTopic:ScalarValues::Boolean;
    abstract attribute feedbackTopicType:FeedbackTopicType;
    abstract attribute inputParameters:LibDTAttributes[0..*];
    abstract attribute constInputParameters:ConstAttributes[0..*];
    abstract attribute outputParameters:LibDTAttributes[0..*];

    abstract part def LibTwinStrategyAction{
        abstract attribute redefines name;
        abstract attribute redefines description[0..1];
        abstract attribute redefines external;
        abstract attribute redefines pathToCode;
        abstract attribute redefines inputParameters[0..*];
        abstract attribute redefines outputParameters[0..*];
        abstract attribute redefines strategyType;
        abstract attribute redefines customPayload[0..1];
        abstract attribute redefines feedbackTopicType[0..1];
        abstract part redefines componentTopic[0..1];
        abstract attribute redefines externalTopic[0..1];
    }




    enum def AttributeDataType :> TwinEnum{
        STRING;
        DOUBLE;
        INTEGER;
        VECTOR_DOUBLE;
        VECTOR_INTEGER;
        VECTOR_STRING;

    }

    enum def FeedbackTopicType :> TwinEnum{
        EXTERN;
        INTERN;
        NOFEEDBACK;
    }
    attribute def LibDTAttributes{
        attribute dataType:AttributeDataType[0..1];
    }

    attribute def ConstAttributes specializes LibDTAttributes{
        attribute value:ScalarValues::String;
    }

    enum def LibTwinDataBaseType :> TwinEnum{
        RELATIONAL;
        TIMESERIES;
    }



    enum def ComparisonOperator :> TwinEnum{
        GREATER_THAN;
        LESS_THAN;
        EQUAL;
        GREATER_EQUAL;
        LESS_EQUAL;
        NOT_EQUAL;
    }
    enum def StrategyType :> TwinEnum{
        LAMBDA;
    }

}