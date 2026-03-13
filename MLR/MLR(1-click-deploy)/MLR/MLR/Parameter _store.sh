 aws ssm put-parameter `
  --name "/mlr/aws-ls/dynamo_db/tables/documents" `
  --value "mlr_user_document_history" `
  --type String `
  --tags Key=Name,Value=mlr

 aws ssm put-parameter `
  --name "MLR_STEP_FUNCTION_ARN" `
  --value "arn:aws:states:us-east-1:969385807621:stateMachine:mlrWorkflowStateMachine" `
  --type String `
  --tags Key=Name,Value=mlr


 aws ssm put-parameter `
  --name "MLR_SOURCE_BUCKET" `
  --value "mlr-data-source" `
  --type String `
  --tags Key=Name,Value=mlr

 aws ssm put-parameter `
  --name "MLR_SOURCE_PREFIX" `
  --value "data/UserDataFiles/" `
  --type String `
  --tags Key=Name,Value=mlr

 aws ssm put-parameter `
  --name "MLR_VITE_USE_COGNITO_CLIENT_SECRET" `
  --value "147m7jm8p6etsdfikofa83e5e18sh7fu14etfmpb6s01fpvesh1s" `
  --type String `
  --tags Key=Name,Value=mlr

aws ssm put-parameter `
  --name "MLR_USER_DOCUMENTS" `
  --value "mlr_user_documents" `
  --type String `
  --tags Key=Name,Value=mlr

aws ssm put-parameter `
  --name "MLR_AGENT_FINDINGS" `
  --value "mlr_agent_findings" `
  --type String `
  --tags Key=Name,Value=mlr

aws ssm put-parameter `
  --name "MLR_S3_USER_BUCKET" `
  --value "mlr-user-documents" `
  --type String `
  --tags Key=Name,Value=mlr
__________________________________________________________________________________________

aws ssm put-parameter `
  --name "MLR_COMPLIANCE_AGENT_RUNTIME_ARN" `
  --value "arn:aws:bedrock-agentcore:us-east-1:969385807621:runtime/mlr_compliance_agent-Q08nc9FYxa" `
  --type String `
  --tags Key=Name,Value=mlr

aws ssm put-parameter `
  --name "MLR_QUALITY_AGENT_RUNTIME_ARN" `
  --value "arn:aws:bedrock-agentcore:us-east-1:969385807621:runtime/mlr_quality_agent-gpLR0r2FoW" `
  --type String `
  --tags Key=Name,Value=mlr

aws ssm put-parameter `
  --name "MLR_REFERENCE_AGENT_RUNTIME_ARN" `
  --value "arn:aws:bedrock-agentcore:us-east-1:969385807621:runtime/mlr_reference_agent-v3SgPh8aPp" `
  --type String `
  --tags Key=Name,Value=mlr

aws ssm put-parameter `
  --name "MLR_SUPERVISOR_AGENT_RUNTIME_ARN" `
  --value "arn:aws:bedrock-agentcore:us-east-1:969385807621:runtime/mlr_supervisor_agent-5ywtkmGnn2" `
  --type String `
  --tags Key=Name,Value=mlr

aws ssm put-parameter `
  --name "MLR_CONTENT_ANALYSIS_AGENT_RUNTIME_ARN" `
  --value "arn:aws:bedrock-agentcore:us-east-1:969385807621:runtime/mlr_ca_agent-xDyEv14WEg" `
  --type String `
  --tags Key=Name,Value=mlr

aws ssm put-parameter `
  --name "MLR_RISK_ANALYSIS_AGENT_RUNTIME_ARN" `
  --value "arn:aws:bedrock-agentcore:us-east-1:969385807621:runtime/mlr_risk_analysis_agent-B326pgBuvg" `
  --type String `
  --tags Key=Name,Value=mlr

aws ssm put-parameter `
  --name "MLR_RISK_ANALYSIS_AGENT_FINDINGS_S3_BUCKET" `
  --value "mlr-risk-analysis-agent-findings" `
  --type String `
  --tags Key=Name,Value=mlr

aws ssm put-parameter `
  --name "MLR_REDSHIFT_WORKGROUP" `
  --value "mlr-workgroup" `
  --type String `
  --tags Key=Name,Value=mlr

aws ssm put-parameter `
  --name "MLR_REDSHIFT_DATABASE" `
  --value "mlr_db" `
  --type String `
  --tags Key=Name,Value=mlr

aws ssm put-parameter `
  --name "MLR_REDSHIFT_TABLE" `
  --value "mart_findings" `
  --type String `
  --tags Key=Name,Value=mlr

aws ssm put-parameter `
  --name "MLR_REDSHIFT_SECRET_ARN" `
  --value "arn:aws:secretsmanager:us-east-1:969385807621:secret:mlr-redshift-serverless-credentials-new-7Xapm4" `
  --type String `
  --tags Key=Name,Value=mlr
