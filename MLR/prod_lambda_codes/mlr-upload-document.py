import uuid
import json
import boto3
import base64
from datetime import datetime, timezone

# =========================
# Config
# =========================
AWS_REGION = "us-east-1"

def get_parameter_value(name: str) -> str:
    ssm = boto3.client("ssm", region_name=AWS_REGION)
    response = ssm.get_parameter(Name=name, WithDecryption=True)
    return response["Parameter"]["Value"]

s3 = boto3.client("s3", region_name=AWS_REGION)
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
stepfunctions = boto3.client("stepfunctions", region_name=AWS_REGION)

S3_BUCKET = get_parameter_value("MLR_S3_BUCKET")
DDB_TABLE = get_parameter_value("MLR_DDB_TABLE")
STEP_FUNCTION_ARN = get_parameter_value("MLR_STEP_FUNCTION_ARN") 

table = dynamodb.Table(DDB_TABLE)

# =========================
# Timestamp
# =========================
def generate_timestamp():
    now = datetime.now(timezone.utc)
    return now.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

# =========================
# Lambda handler
# =========================
def lambda_handler(event, context):
    try:
        payload = event.get("body")

        if event.get("isBase64Encoded"):
            payload = base64.b64decode(payload).decode("utf-8")

        body = json.loads(payload)

        user_id = body["user_id"]
        file_name = body["file_name"]
        file_base64 = body["file"]

        doc_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        timestamp = generate_timestamp()
        state=1

        file_extension = file_name.split(".")[-1].lower()
        s3_key = f"{user_id}/{doc_id}.{file_extension}"
        s3_path = f"s3://{S3_BUCKET}/{s3_key}"

        file_bytes = base64.b64decode(file_base64)

        # Upload to S3
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=file_bytes,
            ContentType="application/pdf"
        )

        # Save metadata
        table.put_item(
            Item={
                "user_doc_id": f"{user_id}:{doc_id}",
                "timestamp": timestamp,
                "raw_s3_path": s3_path,
                "file_name": file_name,
                "state": state,
                "run_id": run_id
            }
        )

        # Invoke Step Function
        stepfunctions.start_execution(
            stateMachineArn=STEP_FUNCTION_ARN,
            name=run_id,
            input=json.dumps({
                "user_id": user_id,
                "doc_id": doc_id,
                "s3_path": s3_path,
                "timestamp": timestamp, 
                "state": 1
            })
        )

        return {
            "statusCode": 200,
            "body":json.dumps({
                
                "user_id": user_id,
                "doc_id": doc_id,
                "s3_path": s3_path,
                "run_id": run_id,
                "state": state
            })
        }

    except Exception as e:
        print("ERROR:", str(e))
        return {
            "statusCode": 500,
            "body":json.dumps({
                "message": str(e)
            })
        }