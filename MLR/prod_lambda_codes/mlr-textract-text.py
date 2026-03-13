import json
import time
import boto3
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
textract = boto3.client("textract", region_name=AWS_REGION)
stepfunctions = boto3.client("stepfunctions", region_name=AWS_REGION)

MLR_USER_DOC = get_parameter_value("MLR_USER_DOCUMENTS")

USER_DOC_TABLE = dynamodb.Table(MLR_USER_DOC)
STEP_FUNCTION_ARN = get_parameter_value("MLR_STEP_FUNCTION_ARN") 

# =========================
# Parse S3 path
# =========================
def parse_s3_path(s3_path: str):
   
    s3_path = s3_path.replace("s3://", "")
    bucket = s3_path.split("/")[0]
    key = "/".join(s3_path.split("/")[1:])
    return bucket, key

def generate_timestamp():
    now = datetime.now(timezone.utc)
    return now.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

def wait_for_textract(job_id):
    """
    Polls Textract job until completion
    """
    while True:
        response = textract.get_document_text_detection(JobId=job_id)
        status = response["JobStatus"]

        if status in ["SUCCEEDED", "FAILED"]:
            return status

        time.sleep(0.5)

# =========================
# Text Extraction
# =========================
def extract_full_text(job_id):
    """
    Retrieves all paginated results
    """
    next_token = None
    full_text = []

    while True:
        if next_token:
            response = textract.get_document_text_detection(
                JobId=job_id,
                NextToken=next_token
            )
        else:
            response = textract.get_document_text_detection(
                JobId=job_id
            )

        for block in response.get("Blocks", []):
            if block["BlockType"] == "LINE":
                full_text.append(block["Text"])

        next_token = response.get("NextToken")
        if not next_token:
            break
        print(next_token)
        print(type(next_token))
    print(full_text)
    print(type(full_text))
    return "\n".join(full_text)

# =========================
# Lambda handler
# =========================
def lambda_handler(event, context):

    try:
        user_id = event["user_id"]
        doc_id = event["doc_id"]
        original_s3_path = event["s3_path"]
        

        bucket, key = parse_s3_path(original_s3_path)

        # Start async Textract job
        start_response = textract.start_document_text_detection(
            DocumentLocation={
                "S3Object": {
                    "Bucket": bucket,
                    "Name": key
                }
            }
        )

        job_id = start_response["JobId"]
        print("Textract Job ID:", job_id)

        # Wait for completion
        status = wait_for_textract(job_id)

        if status != "SUCCEEDED":
            raise Exception(f"Textract job failed with status: {status}")

        # Extract text
        extracted_text = extract_full_text(job_id)
       
        raw_doc_s3_key = f"{user_id}/{doc_id}.txt"
        raw_doc_s3_path = f"s3://{bucket}/{raw_doc_s3_key}"

        s3.put_object(
            Bucket=bucket,
            Key=f"{user_id}/{doc_id}.txt",
            Body=extracted_text.encode("utf-8"),
            ContentType="text/plain; charset=utf-8"
        )
        
        USER_DOC_TABLE.put_item(
            Item={
                "user_id": user_id,
                "timestamp": generate_timestamp(),
                "raw_doc_path": raw_doc_s3_path,
                "doc_id": doc_id
            }
        )

        return {
            "user_id": user_id,
            "doc_id": doc_id,
            "s3_path": raw_doc_s3_path,
            "doc": extracted_text
        }

    except Exception as e:
        raise Exception(f"Lambda failed: {e}")