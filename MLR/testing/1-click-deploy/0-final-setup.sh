#!/bin/bash

#######

USE_CASE="mlr"
USER_GROUP="MLR-user-group"
REGION="us-east-2"

###############
OUT_STACKS_FILE="${USE_CASE}-all-stacks.txt"
touch $OUT_STACKS_FILE

deploy_stack() {
  local STACK_NAME="$1"
  local TEMPLATE_FILE="$2"
  local PARAMS_FILE="$3"
  local REGION="us-east-2"

  if [[ -z "$STACK_NAME" || -z "$TEMPLATE_FILE" || -z "$PARAMS_FILE" ]]; then
    echo "Usage: deploy_stack <stack-name> <template-file> <params-file>" >&2
    return 1
  fi

  echo "🚀 Deploying stack: $STACK_NAME"

  if ! aws cloudformation deploy \
    --stack-name "$STACK_NAME" \
    --parameter-overrides file://"$PARAMS_FILE" \
    --template-file "$TEMPLATE_FILE" \
    --region "$REGION" \
    --capabilities CAPABILITY_NAMED_IAM \
    --no-fail-on-empty-changeset
  then
    echo "❌ Deployment command failed for $STACK_NAME" >&2
    return 1
  fi

#  echo "⏳ Waiting for stack to finish..."

  # Wait for completion explicitly
#  if ! aws cloudformation wait stack-update-complete --stack-name "$STACK_NAME" --region "$REGION" 2>/dev/null; then
#    # If it was a create, fallback to create wait
#    if ! aws cloudformation wait stack-create-complete --stack-name "$STACK_NAME" --region "$REGION"; then
#      echo "❌ Stack failed or rolled back: $STACK_NAME" >&2
#      return 1
#    fi
#  fi

  echo "✔️ Stack finished successfully: $STACK_NAME"
}


UseCaseName="${USE_CASE}"
UserGroupName="${USER_GROUP}"

cat > parms.json <<EOF
{
    "Parameters": {
      "UseCaseName": "${UseCaseName}",
      "UserGroupName": "${UserGroupName}"
    }
}
EOF

STACK_NAME="${UseCaseName}-s3-buckets-infra"
echo "Deploying.. ${STACK_NAME}"
if ! deploy_stack $STACK_NAME 0-s3-buckets.yaml parms.json; then
  echo "Deployment failed ${STACK_NAME}"
  exit 1
fi
echo $STACK_NAME >> $OUT_STACKS_FILE
S3BucketName=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`BucketName`].OutputValue' \
  --output text)

lambdaS3Artifacts=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`LambdaBucketName`].OutputValue' \
  --output text)

jq '.Parameters += {
  "S3BucketName": "'"$S3BucketName"'",
  "lambdaS3Artifacts": "'"$lambdaS3Artifacts"'"
}' parms.json > parms.tmp && mv parms.tmp parms.json

STACK_NAME="${UseCaseName}-vpc-subnet-infra"
echo "Deploying.. ${STACK_NAME}"
if ! deploy_stack $STACK_NAME  1-VPC-Subnet.yaml parms.json; then
  echo "Deployment failed ${STACK_NAME}"
  exit 1
fi
echo $STACK_NAME >> $OUT_STACKS_FILE

VpcId=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`OutVPCID`].OutputValue' \
  --output text)

PrivateSubnet1=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`OutSubnet3`].OutputValue' \
  --output text)

PrivateSubnet2=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`OutSubnet4`].OutputValue' \
  --output text)

PrivateSubnet3=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`OutSubnet5`].OutputValue' \
  --output text)

jq '.Parameters += {
  "VpcId": "'"$VpcId"'",
  "PrivateSubnet1": "'"$PrivateSubnet1"'",
  "PrivateSubnet2": "'"$PrivateSubnet2"'",    
  "PrivateSubnet3": "'"$PrivateSubnet3"'"
}' parms.json > parms.tmp && mv parms.tmp parms.json


# STACK_NAME="${UseCaseName}-aurora-db-infra"
# if ! deploy_stack $STACK_NAME 2-Auroradb_creation.yaml parms.json; then
#   echo "Caller: deployment failed 1 — handle cleanup here." >&2
#   exit 1
# fi
# echo $STACK_NAME >> $OUT_STACKS_FILE

STACK_NAME="${UseCaseName}-redshift-serverless-infra"
if ! deploy_stack $STACK_NAME 3-Redshift.yaml parms.json; then
  echo "Caller: deployment failed 1 — handle cleanup here." >&2
  exit 1
fi
echo $STACK_NAME >> $OUT_STACKS_FILE

LAMBDA_PY="redshift_sql"
STACK_NAME="${USE_CASE}-${LAMBDA_PY//_/}-lambda-infra"
HANDLER=$(cat src/${LAMBDA_PY}.py | grep -E '^def[[:space:]]+[a-zA-Z0-9_]*handler[[:space:]]*\([^)]*\)' \
  | grep -E '\(.*event.*context.*\)|\(.*context.*event.*\)' \
  | sed -E 's/^def[[:space:]]+([a-zA-Z0-9_]+).*/\1/' \
  | head -1)


zip -j ${LAMBDA_PY}-function.zip src/${LAMBDA_PY}.py
aws s3 cp ${LAMBDA_PY}-function.zip s3://${lambdaS3Artifacts}/${LAMBDA_PY}/${LAMBDA_PY}-function.zip

jq '.Parameters += {
  "lambdaHandler": "'"${LAMBDA_PY}.${HANDLER}"'",
  "lambdaS3key": "'"${LAMBDA_PY}/${LAMBDA_PY}-function.zip"'"
}' parms.json > parms.tmp && mv parms.tmp parms.json

if ! deploy_stack $STACK_NAME 4-lambda_to_execute_redshift_sql.yaml parms.json; then
  echo "Caller: deployment failed 1 — handle cleanup here." >&2
  exit 1
fi
echo $STACK_NAME >> $OUT_STACKS_FILE


STACK_NAME="${UseCaseName}-cognito-infra"
if ! deploy_stack $STACK_NAME 5-Cognito_UI.yaml parms.json; then
  echo "Caller: deployment failed 1 — handle cleanup here." >&2
  exit 1
fi
echo $STACK_NAME >> $OUT_STACKS_FILE

STACK_NAME="${UseCaseName}-amazon-aoss-infra"
if ! deploy_stack $STACK_NAME 6-Opensearch-collection.yaml parms.json; then
  echo "Caller: deployment failed 1 — handle cleanup here." >&2
  exit 1
fi
echo $STACK_NAME >> $OUT_STACKS_FILE

STACK_NAME="${UseCaseName}-dynamodb-agent-findings-infra"
if ! deploy_stack $STACK_NAME 7-dynamo-db_mlr_agent_findings.yaml parms.json; then
  echo "Caller: deployment failed 1 — handle cleanup here." >&2
  exit 1
fi
echo $STACK_NAME >> $OUT_STACKS_FILE

AgentFindingsTableName=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`AgentFindingsTableName`].OutputValue' \
  --output text)

STACK_NAME="${UseCaseName}-dynamodb-user-documents-infra"
if ! deploy_stack $STACK_NAME 7-dynamo-db_user_documents.yaml parms.json; then
  echo "Caller: deployment failed 1 — handle cleanup here." >&2
  exit 1
fi
echo $STACK_NAME >> $OUT_STACKS_FILE

UserDocumentsTableName=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`UserDocumentsTableName`].OutputValue' \
  --output text)

STACK_NAME="${UseCaseName}-dynamodb-user-doc-history-infra"
if ! deploy_stack $STACK_NAME 7-dynamo-db-mlr_user_document_history.yaml parms.json; then
  echo "Caller: deployment failed 1 — handle cleanup here." >&2
  exit 1
fi
echo $STACK_NAME >> $OUT_STACKS_FILE

UserDocHistoryTableName=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`UserDocumentHistoryTableName`].OutputValue' \
  --output text)

jq '.Parameters += {
  "AgentFindingsTableName": "'"$AgentFindingsTableName"'",
  "UserDocumentsTableName": "'"$UserDocumentsTableName"'",
  "UserDocHistoryTableName": "'"$UserDocHistoryTableName"'"
}' parms.json > parms.tmp && mv parms.tmp parms.json

STACK_NAME="${UseCaseName}-upload-document-api-infra"
if ! deploy_stack $STACK_NAME 8-api-gateway-upload-document.yaml parms.json; then
  echo "Caller: deployment failed 1 — handle cleanup here." >&2
  exit 1
fi
echo $STACK_NAME >> $OUT_STACKS_FILE

STACK_NAME="${UseCaseName}-textract-lambda-infra"
if ! deploy_stack $STACK_NAME 9-mlr-textract-text-lambda.yaml parms.json; then
  echo "Caller: deployment failed 1 — handle cleanup here." >&2
  exit 1
fi
echo $STACK_NAME >> $OUT_STACKS_FILE

STACK_NAME="${UseCaseName}-cloudfront-ui-infra"
if ! deploy_stack $STACK_NAME 10-cloudfront_S3_template.yaml parms.json; then
  echo "Caller: deployment failed 1 — handle cleanup here." >&2
  exit 1
fi
echo $STACK_NAME >> $OUT_STACKS_FILE

STACK_NAME="${UseCaseName}-kpi-api-gateway-infra"
if ! deploy_stack $STACK_NAME 12-Lambda_kpi_api_gateway_.yaml parms.json; then
  echo "Caller: deployment failed 1 — handle cleanup here." >&2
  exit 1
fi
echo $STACK_NAME >> $OUT_STACKS_FILE

echo "All infra deployed succesfully"
exit 0



