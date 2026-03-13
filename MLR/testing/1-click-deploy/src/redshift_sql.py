import json
import time
import boto3

def get_parameter_value(parameter_name):
    """Fetch a parameter from AWS Systems Manager Parameter Store."""
    try:
        ssm_client = boto3.client("ssm")
        response = ssm_client.get_parameter(Name=parameter_name, WithDecryption=True)
        return response["Parameter"]["Value"]
    except Exception as e:
        print(f"Error fetching parameter {parameter_name}: {str(e)}")
        return None


# ----------------------
# Configuration 
# ----------------------
WORKGROUP = get_parameter_value("REDSHIFT_WORKGROUP")
DATABASE = get_parameter_value("SC_REDSHIFT_DATABASE")
SECRET_ARN = get_parameter_value("SC_REDSHIFT_SECRET_ARN")

DEFAULT_SQL_LIMIT = 1000
SQL_POLL_INTERVAL_SECONDS = 0.5
SQL_POLL_MAX_SECONDS = 30.0


def lambda_handler(event, context):
    """
    Lambda wrapper for execute_redshift_sql tool.
    Expected event payload:
    {
        "sql_query": "SELECT 1",
        "return_results": true
    }
    """
    sql_query = event.get("sql_query")
    return_results = event.get("return_results", True)

    if not sql_query:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Missing 'sql_query' in request"})
        }

    client = boto3.client("redshift-data")

    try:
        resp = client.execute_statement(
            WorkgroupName=WORKGROUP,
            Database=DATABASE,
            SecretArn=SECRET_ARN,
            Sql=sql_query
        )
        stmt_id = resp["Id"]
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({
                "status": "error",
                "message": f"execute_statement error: {str(e)}"
            })
        }

    elapsed = 0.0
    status = None

    while elapsed < SQL_POLL_MAX_SECONDS:
        try:
            status_resp = client.describe_statement(Id=stmt_id)
            status = status_resp.get("Status")
        except Exception as e:
            return {
                "statusCode": 500,
                "body": json.dumps({
                    "status": "error",
                    "message": f"describe_statement error: {str(e)}"
                })
            }

        if status in ("FINISHED", "ABORTED", "FAILED"):
            break

        time.sleep(SQL_POLL_INTERVAL_SECONDS)
        elapsed += SQL_POLL_INTERVAL_SECONDS

    if status != "FINISHED":
        try:
            status_resp = client.describe_statement(Id=stmt_id)
            err = status_resp.get("Error")
        except Exception:
            err = "Statement did not finish within time limit."

        return {
            "statusCode": 500,
            "body": json.dumps({
                "status": status,
                "message": err
            })
        }

    if not return_results:
        return {
            "statusCode": 200,
            "body": json.dumps({
                "status": "finished",
                "statement_id": stmt_id
            })
        }

    # Retrieve results
    try:
        results = client.get_statement_result(Id=stmt_id)
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({
                "status": "error",
                "message": f"get_statement_result error: {str(e)}"
            })
        }

    column_info = [c["name"] for c in results.get("ColumnMetadata", [])]
    records = []

    for row in results.get("Records", []):
        parsed_row = {}
        for idx, cell in enumerate(row):
            col_name = column_info[idx] if idx < len(column_info) else f"col_{idx}"
            if "stringValue" in cell:
                parsed_row[col_name] = cell["stringValue"]
            elif "blobValue" in cell:
                parsed_row[col_name] = cell["blobValue"]
            elif "doubleValue" in cell:
                parsed_row[col_name] = cell["doubleValue"]
            elif "longValue" in cell:
                parsed_row[col_name] = cell["longValue"]
            elif "booleanValue" in cell:
                parsed_row[col_name] = cell["booleanValue"]
            elif "isNull" in cell and cell["isNull"]:
                parsed_row[col_name] = None
            else:
                parsed_row[col_name] = list(cell.values())[0] if cell else None

        records.append(parsed_row)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "status": "finished",
            "rows": records,
            "statement_id": stmt_id
        })
    }
