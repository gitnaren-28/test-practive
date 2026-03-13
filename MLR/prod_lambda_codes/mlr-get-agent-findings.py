import json
import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

# ======================
# Config
# ======================
AWS_REGION = "us-east-1"

def get_parameter_value(name: str) -> str:
    ssm = boto3.client("ssm", region_name=AWS_REGION)
    response = ssm.get_parameter(Name=name, WithDecryption=True)
    return response["Parameter"]["Value"]

AGENT_FINDINGS_TABLE = get_parameter_value("MLR_AGENT_FINDINGS")
USER_DOC_HISTORY = get_parameter_value("MLR_USER_DOC_HISTORY")
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
findings_table = dynamodb.Table(AGENT_FINDINGS_TABLE)

user_document_history = dynamodb.Table(USER_DOC_HISTORY)

# ======================
# Lambda Handler
# ======================
def lambda_handler(event, context):

    try:

# ======================
# Get doc_id from query param
# ======================
        query_params = event.get("queryStringParameters")

        if not query_params or "doc_id" not in query_params:
            return response(400, {
                "error": "doc_id query parameter is required"
            })

        doc_id = query_params["doc_id"]
        user_id = query_params["user_id"]

# ======================
# Query DynamoDB
# ======================
        findings_response = findings_table.query(
            KeyConditionExpression=Key("doc_id").eq(doc_id),
            ScanIndexForward=False,
            Limit=1
        )

        items = findings_response.get("Items", [])

        if not items:
            return response(404, {
                "error": "Document not found",
                "doc_id": doc_id
            })

        findings_item = items[0]

        exisiting_documents = user_document_history.query(
            KeyConditionExpression=Key("user_doc_id").eq(f"{user_id}:{doc_id}"),
            ScanIndexForward=False,
            Limit=1
        )
        exisiting_documents_items = exisiting_documents.get("Items", [])
        matching_doc = exisiting_documents_items[0]

        return response(200, {
            "doc_id": findings_item.get("doc_id"),
            "original_run_id": matching_doc.get("run_id"),
            "timestamp": findings_item.get("timestamp"),
            "findings": findings_item.get("findings")
        })

    except ClientError as e:

        print("DynamoDB error:", str(e))

        return response(500, {
            "error": "Database error",
            "details": str(e)
        })

    except Exception as e:

        print("Error:", str(e))

        return response(500, {
            "error": "Internal error",
            "details": str(e)
        })


def response(status, body):

    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json"
        },
        "body": json.dumps(body)
    }