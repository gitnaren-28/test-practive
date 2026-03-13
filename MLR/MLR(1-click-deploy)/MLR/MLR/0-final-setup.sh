#!/bin/bash

#######

USE_CASE="mlr"
USER_GROUP="mlr"
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
if ! deploy_stack $STACK_NAME 16-S3-bucket.yaml parms.json; then
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
if ! deploy_stack $STACK_NAME  00-vpc-subnet.yaml parms.json; then
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


STACK_NAME="${UseCaseName}-amazon-aoss-infra"
if ! deploy_stack $STACK_NAME 6-Opensearch-collection.yaml parms.json; then
  echo "Caller: deployment failed 1 — handle cleanup here." >&2
  exit 1
fi
echo $STACK_NAME >> $OUT_STACKS_FILE

STACK_NAME="${UseCaseName}-dynamodb-infra"
if ! deploy_stack $STACK_NAME 7-dynamodb.yaml parms.json; then
  echo "Caller: deployment failed 1 — handle cleanup here." >&2
  exit 1
fi
echo $STACK_NAME >> $OUT_STACKS_FILE

DynamoDBTableName=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`ChatMessagesTableName`].OutputValue' \
  --output text)

DynamoDBTableName1=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`ChatSessionsTableName`].OutputValue' \
  --output text)

LAMBDA_PY="chat_history"
STACK_NAME="${USE_CASE}-${LAMBDA_PY//_/}-lambda-infra"
HANDLER=$(cat src/${LAMBDA_PY}.py | grep -E '^def[[:space:]]+[a-zA-Z0-9_]*handler[[:space:]]*\([^)]*\)' \
  | grep -E '\(.*event.*context.*\)|\(.*context.*event.*\)' \
  | sed -E 's/^def[[:space:]]+([a-zA-Z0-9_]+).*/\1/' \
  | head -1)


zip -j ${LAMBDA_PY}-function.zip src/${LAMBDA_PY}.py
aws s3 cp ${LAMBDA_PY}-function.zip s3://${lambdaS3Artifacts}/${LAMBDA_PY}/${LAMBDA_PY}-function.zip

jq '.Parameters += {
  "lambdaHandler": "'"${LAMBDA_PY}.${HANDLER}"'",
  "DynamoDBTableName": "'"$DynamoDBTableName"'", 
  "DynamoDBTableName1": "'"$DynamoDBTableName1"'", 
  "lambdaS3key": "'"${LAMBDA_PY}/${LAMBDA_PY}-function.zip"'"
}' parms.json > parms.tmp && mv parms.tmp parms.json


if ! deploy_stack $STACK_NAME 8-API-Gateway.yaml parms.json; then
  echo "Caller: deployment failed 1 — handle cleanup here." >&2
  exit 1
fi
echo $STACK_NAME >> $OUT_STACKS_FILE

STACK_NAME="${UseCaseName}-cloudfront-UI-infra"
if ! deploy_stack $STACK_NAME 10-cloudfront-s3.yaml parms.json; then
  echo "Caller: deployment failed 1 — handle cleanup here." >&2
  exit 1
fi
echo $STACK_NAME >> $OUT_STACKS_FILE

LAMBDA_PY="kpi_api"
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

if ! deploy_stack $STACK_NAME 11-lambda_kpi_api.yaml parms.json; then
  echo "Caller: deployment failed 1 — handle cleanup here." >&2
  exit 1
fi
echo $STACK_NAME >> $OUT_STACKS_FILE

KPIAPIFunction=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`LambdaFunc`].OutputValue' \
  --output text)

LambdaARN=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`LambdaFuncARN`].OutputValue' \
  --output text)

jq '.Parameters += {
  "KPIAPIFunction": "'"$KPIAPIFunction"'",
  "LambdaARN": "'"$LambdaARN"'"
}' parms.json > parms.tmp && mv parms.tmp parms.json
STACK_NAME="${UseCaseName}-kpi-gateway-infra"

if ! deploy_stack $STACK_NAME 12-API-Gateway-kpi.yaml parms.json; then
  echo "Caller: deployment failed 1 — handle cleanup here." >&2
  exit 1
fi
echo $STACK_NAME >> $OUT_STACKS_FILE

echo "All infra deployed succesfully"
exit 0



