import json
import boto3
import logging
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Configuration
AWS_REGION = "us-east-1"
def get_parameter_value(name: str) -> str:
    ssm = boto3.client("ssm", region_name=AWS_REGION)
    response = ssm.get_parameter(Name=name, WithDecryption=True)
    return response["Parameter"]["Value"]

MLR_RISK_ANALYSIS_AGENT_RUNTIME_ARN = get_parameter_value("MLR_RISK_ANALYSIS_AGENT_RUNTIME_ARN")

# S3 Configuration
S3_BUCKET = get_parameter_value("MLR_RISK_ANALYSIS_AGENT_FINDINGS_S3_BUCKET")

# DynamoDB Configuration
DYNAMODB_TABLE = get_parameter_value("MLR_USER_DOC_HISTORY")

# Redshift Configuration
REDSHIFT_WORKGROUP = get_parameter_value("MLR_REDSHIFT_WORKGROUP")
REDSHIFT_DATABASE = get_parameter_value("MLR_REDSHIFT_DATABASE")
REDSHIFT_TABLE = get_parameter_value("MLR_REDSHIFT_TABLE")
REDSHIFT_SECRET_ARN = get_parameter_value("MLR_REDSHIFT_SECRET_ARN")

# Initialize AWS clients
try:
    agentcore_client = boto3.client('bedrock-agentcore', region_name=AWS_REGION)
    s3_client = boto3.client('s3', region_name=AWS_REGION)
    dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
    dynamodb_table = dynamodb.Table(DYNAMODB_TABLE)
    redshift_client = boto3.client('redshift-data', region_name=AWS_REGION)
    logger.info("All AWS clients initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize AWS clients: {e}")
    agentcore_client = None


def save_to_s3(user_id: str, doc_id: str, run_id: str, content: dict) -> str:
    """
    Save agent response to S3
    
    Args:
        user_id: User identifier
        doc_id: Document identifier
        run_id: Run identifier
        content: Agent response content
    
    Returns:
        S3 URI of saved file
    """
    object_key = f"{user_id}/risk_assessment_{doc_id}_{run_id}.json"
    
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=object_key,
        Body=json.dumps(content, indent=2).encode("utf-8"),
        ContentType="application/json"
    )
    
    s3_uri = f"s3://{S3_BUCKET}/{object_key}"
    logger.info(f"Saved to S3: {s3_uri}")
    return s3_uri


def update_dynamodb_record(
    user_doc_id: str,
    s3_path: str | None = None,
    state_value: str | None = "4",
):
    """
    Update DynamoDB record with optional fields.

    Args:
        user_doc_id: Combined user_id:doc_id
        s3_path: (Optional) S3 URI where response is stored
        state_value: (Optional) New state value (e.g., "4")
    """

    update_expressions = []
    expression_attribute_values = {}
    expression_attribute_names = {}

    if s3_path is not None:
        update_expressions.append("ra_agent_s3_path = :s3")
        expression_attribute_values[":s3"] = s3_path

    if state_value is not None:
        update_expressions.append("#st = :state")
        expression_attribute_names["#st"] = "state"
        expression_attribute_values[":state"] = state_value

    if not update_expressions:
        logger.warning("No fields provided to update.")
        return

    exisiting_documents = dynamodb_table.query(
        KeyConditionExpression=Key("user_doc_id").eq(user_doc_id),
        ScanIndexForward=False,
        Limit=1
    )
    exisiting_documents_items = exisiting_documents.get("Items", [])
    matching_doc = exisiting_documents_items[0]

    dynamodb_table.update_item(
        Key={
            "user_doc_id": user_doc_id,
            "timestamp": matching_doc.get("timestamp")
        },
        UpdateExpression="SET " + ", ".join(update_expressions),
        ExpressionAttributeNames=expression_attribute_names if expression_attribute_names else None,
        ExpressionAttributeValues=expression_attribute_values,
    )

    logger.info(
        f"Updated DynamoDB record for {user_doc_id} "
        f"(s3_path={s3_path}, state={state_value})"
    )


def escape_sql_string(value: str) -> str:
    """Escape single quotes for SQL"""
    if isinstance(value, str):
        return value.replace("'", "''")
    return str(value)


def insert_to_redshift(user_doc_id: str, user_id: str, doc_id: str, run_id: str, 
                       s3_path: str, agent_response: dict):
    """
    Insert record into Redshift
    
    Args:
        user_doc_id: Combined user_id:doc_id
        user_id: User identifier
        doc_id: Document identifier
        run_id: Run identifier
        s3_path: S3 URI
        agent_response: Agent response containing heading, severity, recommendation, findings
    """
    import time
    
    # Extract fields from agent response
    heading = escape_sql_string(agent_response.get("heading", ""))
    severity = escape_sql_string(agent_response.get("severity", ""))
    recommendation = escape_sql_string(agent_response.get("recommendation", ""))
    findings = escape_sql_string(json.dumps(agent_response.get("findings", [])))
    current_timestamp = datetime.now(timezone.utc).isoformat()
    
    # Build SQL
    sql = f"""
        INSERT INTO {REDSHIFT_TABLE} 
        (doc_id, user_id, run_id, ra_agent_s3_path, heading, severity, recommendation, findings, timestamp)
        VALUES 
        ('{escape_sql_string(user_doc_id)}', '{escape_sql_string(user_id)}', '{escape_sql_string(run_id)}', 
         '{escape_sql_string(s3_path)}', '{heading}', '{severity}', '{recommendation}', '{findings}', '{current_timestamp}')
    """
    
    logger.info(f"Executing Redshift INSERT")
    
    response = redshift_client.execute_statement(
        WorkgroupName=REDSHIFT_WORKGROUP,
        Database=REDSHIFT_DATABASE,
        SecretArn=REDSHIFT_SECRET_ARN,
        Sql=sql
    )
    
    statement_id = response.get('Id')
    
    # Wait for completion (max 10 seconds)
    for _ in range(10):
        time.sleep(1)
        status_response = redshift_client.describe_statement(Id=statement_id)
        status = status_response.get('Status')
        
        if status == 'FINISHED':
            logger.info(f"Redshift INSERT completed successfully")
            return {"status": "SUCCESS"}
        elif status in ['FAILED', 'ABORTED']:
            error = status_response.get('Error', 'Unknown error')
            logger.error(f"Redshift INSERT failed: {error}")
            return {"status": "FAILED", "error": error}
    
    logger.warning("Redshift INSERT timed out, may still complete")
    return {"status": "TIMEOUT"}


def lambda_handler(event, context):
    """
    Lambda handler to invoke Risk Analysis Agent and handle all storage operations
    
    Args:
        event (dict): Input event containing user_id, doc_id, run_id, timestamp, findings
        context: Lambda context object
    
    Returns:
        dict: Response with status and data/error
    """
    logger.info(f"Received event: {json.dumps(event)}")
    
    # Validate client initialization
    if agentcore_client is None:
        return {
            "statusCode": 500,
            "body": json.dumps({"status": "error", "error": "AWS clients not initialized"})
        }
    
    # Extract required fields
    user_id = event.get("user_id")
    doc_id = event.get("doc_id")
    run_id = event.get("run_id")
    findings = event.get("findings")
    
    # Validate required fields
    missing_fields = []
    if not user_id: missing_fields.append("user_id")
    if not doc_id: missing_fields.append("doc_id")
    if not run_id: missing_fields.append("run_id")
    if not findings: missing_fields.append("findings")
    
    if missing_fields:
        error_msg = f"Missing required fields: {', '.join(missing_fields)}"
        logger.error(error_msg)
        return {
            "statusCode": 400,
            "body": json.dumps({"status": "error", "error": error_msg})
        }
    
    # Construct user_doc_id
    user_doc_id = f"{user_id}:{doc_id}"
    logger.info(f"Processing user_doc_id: {user_doc_id}")
    
    try:
        # ============================================================
        # STEP 1: Invoke Risk Analysis Agent
        # ============================================================
        logger.info("Step 1: Invoking Risk Analysis Agent...")
        
        agent_input = {"findings": findings}
        payload_dict = {"prompt": json.dumps(agent_input)}
        payload_bytes = json.dumps(payload_dict).encode('utf-8')
        
        response = agentcore_client.invoke_agent_runtime(
            agentRuntimeArn=MLR_RISK_ANALYSIS_AGENT_RUNTIME_ARN,
            payload=payload_bytes
        )
        
        print(f"Response keys: {response.keys()}")
        
        response_body = response['response'].read()
        print(f"Raw response body length: {len(response_body) if response_body else 0}")
        
        # Decode bytes to string if needed
        if isinstance(response_body, bytes):
            response_body = response_body.decode('utf-8')
        
        print(f"Decoded response body: {response_body[:500] if response_body else 'EMPTY'}")
        
        # Try to parse as JSON, handle text responses
        agent_response = None
        if response_body and response_body.strip():
            # Remove surrounding quotes if present (agent returns quoted string)
            clean_body = response_body.strip()
            if clean_body.startswith('"') and clean_body.endswith('"'):
                clean_body = clean_body[1:-1]
                # Unescape the string
                clean_body = clean_body.replace('\\n', '\n').replace('\\"', '"')
            
            try:
                agent_response = json.loads(clean_body)
            except json.JSONDecodeError:
                # Response is plain text, wrap it
                print(f"Response is plain text, not JSON")
                agent_response = {
                    "heading": "Risk Assessment Analysis",
                    "severity": "LOW",
                    "recommendation": clean_body[:500],
                    "findings": [],
                    "raw_response": clean_body
                }
        else:
            raise ValueError(f"Empty response from agent")
        
        print(f"Agent response parsed successfully")
        
        # ============================================================
        # STEP 2: Save response to S3
        # ============================================================
        logger.info("Step 2: Saving response to S3...")
        
        # Add metadata to response before saving
        full_response = {
            "user_doc_id": user_doc_id,
            "user_id": user_id,
            "doc_id": doc_id,
            "run_id": run_id,
            **agent_response
        }
        
        s3_path = save_to_s3(user_id, doc_id, run_id, full_response)            
        
        # ============================================================
        # STEP 4: Insert into Redshift
        # ============================================================
        logger.info("Step 3: Inserting into Redshift...")
        
        redshift_result = insert_to_redshift(
            user_doc_id, user_id, doc_id, run_id, s3_path, agent_response
        )
        
        # ============================================================
        # STEP 5: Update DynamoDB state to "4"
        # ============================================================
        logger.info("Step 4: Updating DynamoDB state to 4...")
        
        update_dynamodb_record(user_doc_id, s3_path)
        
        # ============================================================
        # Return success response
        # ============================================================
        logger.info("All steps completed successfully!")
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "status": "success",
                "user_doc_id": user_doc_id,
                "s3_path": s3_path,
                "redshift_status": redshift_result.get("status"),
                "state": "4",
                "data": agent_response
            })
        }
    
    except Exception as e:
        error_msg = f"Risk Analysis processing failed: {str(e)}"
        logger.error(error_msg)
        logger.exception("Full exception traceback:")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "status": "error",
                "error": error_msg,
                "error_type": type(e).__name__
            })
        }