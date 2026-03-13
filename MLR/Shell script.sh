
# Below is the command to run Cognito_UI.yaml 
aws cloudformation deploy `
 --template-file Cognito_UI.yaml `
 --stack-name mlr-cognito-infra `
 --capabilities CAPABILITY_NAMED_IAM

# Below is the command to run api-gateway.yaml
 aws cloudformation deploy `
 --template-file api-gateway.yaml `
 --stack-name mlr-api-gateway-infra `
 --capabilities CAPABILITY_NAMED_IAM

# Below is the command to run dynamodb.yaml
 aws cloudformation create-stack `
 --stack-name mlr-dynamodb-infra `
 --template-body file://dynamo-db.yaml `
 --capabilities CAPABILITY_NAMED_IAM

# Below is the command to run mlr_user_document_history.yaml
 aws cloudformation create-stack `
 --stack-name mlr-user-document-history-dynamodb-infra `
 --template-body file://dynamo-db-mlr_user_document_history.yaml `
 --capabilities CAPABILITY_NAMED_IAM

# Below is the command to run the mlr Lambda_kpi_api_gateway_.yaml
 aws cloudformation deploy `
--template-file Lambda_kpi_api_gateway_.yaml `
--stack-name mlr-kpi-api-stack `
--capabilities CAPABILITY_NAMED_IAM `
--parameter-overrides UseCaseName=mlr StageName=v1

# Below is the command to run the cloudfront_S3_template.yaml
aws cloudformation create-stack `
  --stack-name mlr-cloudfront-s3-infra `
  --template-body file://cloudfront_S3_template.yaml `
  --parameters ParameterKey=UseCaseName,ParameterValue=mlr

#  Below is the command to run the mlr-textract-text.yaml
aws cloudformation deploy `
  --template-file "Redshift Data\MLR\mlr-textract-text.yaml" `
  --stack-name mlr-textract-text `
  --capabilities CAPABILITY_IAM `

# Below is the command to run the dynamo-db_user_documents.yaml
  aws cloudformation create-stack `
  --stack-name mlr-user-documents-table-infra `
  --template-body file://dynamo-db_user_documents.yaml `
  --parameters ParameterKey=NamePrefix,ParameterValue=mlr

# Below is the command to run the mlr-s3-bucket.yaml
aws cloudformation create-stack `
--stack-name mlr-s3-bucket `
--template-body file://mlr-s3-bucket.yaml `
--region us-east-1


# Below is the command to run the mlr-11-lambdas.yaml

aws cloudformation deploy `
  --template-file mlr_11_lambdas.yaml `
  --stack-name mlr-lambdas-infra `
  --capabilities CAPABILITY_NAMED_IAM `
  --region us-east-1

# Below is the command to run the mlr-reviewer-api.yaml
aws cloudformation deploy `
 --template-file mlr-reviewer-api.yaml `
 --stack-name mlr-reviewer-api-infra `
 --capabilities CAPABILITY_NAMED_IAM `
 --region us-east-1


# Below is the command to run the mlr-reviewer-agent.yaml
 aws cloudformation deploy `
  --template-file mlr-reviewer-agent.yaml `
  --stack-name mlr-reviewer-agent-infra `
  --capabilities CAPABILITY_NAMED_IAM `
  --region us-east-1



  aws cloudformation update-stack `
  --template-body file://api-gateway-agent-findings.yaml `
  --stack-name mlr-agent-findings-api-infra `
  --parameters ParameterKey=LambdaFunctionName,ParameterValue=mlr-get-agent-findings `
  --capabilities CAPABILITY_IAM




  aws cloudformation update-stack `
  --template-body file://api-gateway.yaml `
  --stack-name mlr-api-gateway-infra `
  --parameters ParameterKey=LambdaFunctionName,ParameterValue=mlr-upload-document `
  --capabilities CAPABILITY_IAM


aws cloudformation update-stack `
  --template-body file://Lambda_kpi_api_gateway_.yaml `
  --stack-name mlr-kpi-api-stack `
  --capabilities CAPABILITY_NAMED_IAM

# Below is the command to run the mlr-reviewer-kpi-api.yaml
aws cloudformation create-stack `
  --stack-name mlr-reviewer-kpi-api-infra `
  --template-body file://mlr-reviewer-kpi-api.yaml `
  --capabilities CAPABILITY_NAMED_IAM `
  --region us-east-1


