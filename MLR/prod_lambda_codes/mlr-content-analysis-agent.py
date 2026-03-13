import json
import boto3

AWS_REGION = "us-east-1"
def get_parameter_value(name: str) -> str:
    ssm = boto3.client("ssm", region_name=AWS_REGION)
    response = ssm.get_parameter(Name=name, WithDecryption=True)
    return response["Parameter"]["Value"]

agentcore_client = boto3.client("bedrock-agentcore", region_name=AWS_REGION)
MLR_CONTENT_ANALYSIS_AGENT_RUNTIME_ARN = get_parameter_value("MLR_CONTENT_ANALYSIS_AGENT_RUNTIME_ARN")

def lambda_handler(event, context):
    try:
        prompt = event.get("prompt")
        if not prompt: raise Exception("Prompt cannot be empty")

        kwargs = {
            "agentRuntimeArn": MLR_CONTENT_ANALYSIS_AGENT_RUNTIME_ARN,
            "payload": json.dumps(event),
        }

        resp = agentcore_client.invoke_agent_runtime(**kwargs)
        body = resp["response"].read()
        response = json.loads(body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else body)
        response.update({"finding_type": "content_analysis_agent"})
        return response
    except Exception as e:
        raise Exception(f"content analysis agent invocation failed: {e}")