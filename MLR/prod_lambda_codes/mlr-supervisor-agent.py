import json
import boto3

AWS_REGION = "us-east-1"
def get_parameter_value(name: str) -> str:
    ssm = boto3.client("ssm", region_name=AWS_REGION)
    response = ssm.get_parameter(Name=name, WithDecryption=True)
    return response["Parameter"]["Value"]

agentcore_client = boto3.client("bedrock-agentcore", region_name=AWS_REGION)
MLR_SUPERVISOR_AGENT_RUNTIME_ARN = get_parameter_value("MLR_SUPERVISOR_AGENT_RUNTIME_ARN")

def lambda_handler(event, context):
    try:
        prompt = event.get("prompt")
        doc = event.get("doc")
        if not prompt: raise Exception("Prompt cannot be empty")

        kwargs = {
            "agentRuntimeArn": MLR_SUPERVISOR_AGENT_RUNTIME_ARN,
            "payload": json.dumps(prompt),
        }

        resp = agentcore_client.invoke_agent_runtime(**kwargs)
        body = resp["response"].read()
        response = json.loads(body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else body)

        agent_mapping = {
            "content_analysis_agent": get_parameter_value("MLR_CONTENT_ANALYSIS_AGENT_RUNTIME_ARN"),
            "quality_agent": get_parameter_value("MLR_QUALITY_AGENT_RUNTIME_ARN"),
            "reference_agent": get_parameter_value("MLR_REFERENCE_AGENT_RUNTIME_ARN"),
            "compliance_agent": get_parameter_value("MLR_COMPLIANCE_AGENT_RUNTIME_ARN")
        }

        lambdas = []
        for each in response["invoke_agents"]:
            lambdas.append({"name": agent_mapping[each],
                            "doc": doc})

        return {
            "statusCode": 200,
            "body": {
                "lambdas": lambdas
            }
        }
    except Exception as e:
        raise Exception(f"supervisor agent invocation failed: {e}")