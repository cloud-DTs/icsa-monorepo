provider "aws" {
  alias  = "eu_central_1"
  region = "eu-central-1"
}


data "archive_file" "ConsumptionStrategy_pipeline_zip" {
  type        = "zip"
  source_dir  = "${path.module}/.build/ConsumptionStrategy_pipeline"
  output_path = "${path.module}/ConsumptionStrategy_pipeline_payload.zip"
}

resource "aws_iam_role" "ConsumptionStrategy_pipeline_role" {
  name = "ConsumptionStrategy_pipeline-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "ConsumptionStrategy_pipeline_policy" {
  role = aws_iam_role.ConsumptionStrategy_pipeline_role.id
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ "Effect" : "Allow", "Action" : ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"], "Resource" : "*" }, { "Effect" : "Allow", "Action" : ["lambda:InvokeFunction"], "Resource" : ["arn:aws:lambda:eu-central-1:717556240325:function:Battery-hot-reader", "arn:aws:lambda:eu-central-1:717556240325:function:PV-hot-reader"] }, { "Effect" : "Allow", "Action" : ["iot:Publish"], "Resource" : ["*"] }]
  })
}

resource "aws_lambda_function" "ConsumptionStrategy_pipeline" {
  filename         = data.archive_file.ConsumptionStrategy_pipeline_zip.output_path
  source_code_hash = data.archive_file.ConsumptionStrategy_pipeline_zip.output_base64sha256
  function_name    = "ConsumptionStrategy_pipeline"
  role             = aws_iam_role.ConsumptionStrategy_pipeline_role.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.13"
  timeout          = 90


  environment {
    variables = {
      PARAMETERS     = "{\"ConsumptionStrategy\": [{\"name\": \"generatedPower\", \"dataType\": \"DOUBLE\", \"strategy_name\": \"production\", \"hot_reader_arn\": \"arn:aws:lambda:eu-central-1:717556240325:function:PV-hot-reader\", \"region\": \"eu-central-1\", \"workspace_id\": \"PV-twinmaker\", \"entity_id\": \"QWB3zi3nv8UNdtvw8Fbkk8\", \"component_name\": \"PVconst_component\", \"property_name\": \"generatedPower\", \"value\": 50.0}, {\"name\": \"chargeValue\", \"dataType\": \"INTEGER\", \"strategy_name\": \"status\", \"hot_reader_arn\": \"arn:aws:lambda:eu-central-1:717556240325:function:Battery-hot-reader\", \"region\": \"eu-central-1\", \"workspace_id\": \"Battery-twinmaker\", \"entity_id\": \"4udMBA6jAnnRf33MNHHP9P\", \"component_name\": \"p16\", \"property_name\": \"charges\"}]}"
      FEEDBACK_TYPE  = "INTERNAL"
      FEEDBACK_TOPIC = "Battery/iot-data"
    }
  }
}

resource "aws_ssm_parameter" "PV_event-registry_production_registry" {
  provider  = aws.eu_central_1
  name      = "/PV/event-registry/production"
  type      = "String"
  overwrite = true
  value     = jsonencode({ targets = [{ type = "lambda", address = aws_lambda_function.ConsumptionStrategy_pipeline.arn }] })
}

resource "aws_ssm_parameter" "Battery_event-registry_status_registry" {
  provider  = aws.eu_central_1
  name      = "/Battery/event-registry/status"
  type      = "String"
  overwrite = true
  value     = jsonencode({ targets = [{ type = "lambda", address = aws_lambda_function.ConsumptionStrategy_pipeline.arn }] })
}