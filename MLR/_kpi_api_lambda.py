import json
import boto3
import decimal
import logging
from boto3.dynamodb.conditions import Attr
import base64
from typing import NamedTuple
import os
from datetime import datetime, timedelta
 
# ---------- Logging Setup ----------
LOGGER = logging.getLogger()
if not LOGGER.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER.setLevel(logging.INFO)
 
# Initialize DynamoDB resources
dynamodb = boto3.resource("dynamodb")
USER_DOC_TABLE_NAME = "mlr_user_document_history"
FINDINGS_TABLE_NAME = "mlr_agent_findings"
user_docs = dynamodb.Table(USER_DOC_TABLE_NAME)
findings_table = dynamodb.Table(FINDINGS_TABLE_NAME)
 
# Initialize Redshift client
redshift_data = boto3.client('redshift-data')
WORKGROUP_NAME = "mlr-workgroup"
DATABASE = "mlr_db"
SECRET_ARN = "arn:aws:secretsmanager:us-east-1:969385807621:secret:mlr-redshift-serverless-credentials-new-7Xapm4"
 
def json_default(obj):
    if isinstance(obj, decimal.Decimal):
        return int(obj) if obj == int(obj) else float(obj)
    return str(obj)
 
def response(code, body):
    return {
        "statusCode": code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Methods": "GET,OPTIONS"
        },
        "body": json.dumps(body, default=json_default)
    }
 
class ParsedEvent(NamedTuple):
    method: str
    path: str
 
def parse_event(event) -> ParsedEvent:
    method = event.get('httpMethod') or event.get('requestContext', {}).get('http', {}).get('method')
    raw_path = event.get('path') or event.get('rawPath') or '/'
    path = normalize_path(raw_path, event)
    return ParsedEvent(method, path)
 
def normalize_path(raw_path: str, event: dict) -> str:
    """Remove stage prefix (/v1, /prod, /$default) if present and trim trailing slash."""
    if not raw_path:
        return "/"
    stage = (
        event.get("requestContext", {}).get("stage")
        or event.get("requestContext", {}).get("http", {}).get("stage")
    )
    if stage and raw_path.startswith(f"/{stage}/"):
        raw_path = raw_path[len(stage) + 2:]
        if not raw_path.startswith("/"):
            raw_path = "/" + raw_path
    if stage and raw_path == f"/{stage}":
        raw_path = "/"
    if len(raw_path) > 1 and raw_path.endswith("/"):
        raw_path = raw_path[:-1]
    return raw_path
 
def lambda_handler(event, context):
    try:
        parsed = parse_event(event)
       
        if parsed.method == 'OPTIONS':
            return response(200, {'message': 'OK'})
       
        if parsed.method == 'GET' and parsed.path == '/dashboard':
            query_params = event.get('queryStringParameters') or {}
            user_id = query_params.get('user_id')
            return handle_dashboard(user_id)
       
        if parsed.method == 'GET' and parsed.path == '/weekly-comparison':
            query_params = event.get('queryStringParameters') or {}
            user_id = query_params.get('user_id')
            return handle_weekly_comparison(user_id)
       
        if parsed.method == 'GET' and parsed.path.startswith('/user-documents/'):
            path_parts = parsed.path.split('/')
            if len(path_parts) >= 3:
                if path_parts[2] == 'run' and len(path_parts) >= 4:
                    run_id = path_parts[3]
                    return handle_get_documents_by_run(run_id)
                else:
                    user_id = path_parts[2]
                    return handle_get_documents_by_user(user_id)
               
        if parsed.method == 'GET' and parsed.path.startswith('/risk-assessment/'):
            path_parts = parsed.path.split('/')
            if len(path_parts) >= 3:
                run_id = path_parts[2]
                return handle_risk_assessment(run_id)
 
       
        return response(404, {'error': f'Route not found: {parsed.path}'})  
       
    except Exception as e:
        LOGGER.exception("Unhandled error in lambda_handler")
        return response(500, {'error': 'Internal server error'})
 
def transform_document(doc, exclude_user_id=False, exclude_run_id=False, findings=None, severity=None):
    user_doc_id = doc.get('user_doc_id', '')
   
    if ':' in user_doc_id:
        user_id, doc_id = user_doc_id.split(':', 1)
    else:
        user_id, doc_id = user_doc_id, ''
   
    result = {
        'doc_id': doc_id,
        'filename': doc.get('file_name', ''),
        'timestamp': doc.get('timestamp'),
        'state': doc.get('state')
    }
   
    if not exclude_user_id:
        result['user_id'] = user_id
   
    if not exclude_run_id:
        result['run_id'] = doc.get('run_id')
   
    if findings is not None:
        result['findings'] = findings
   
    if severity is not None:
        result['severity'] = severity
   
    return result
 
def get_severities_by_user(user_id):
    try:
        sql = f"SELECT run_id, severity FROM mart_findings WHERE user_id = '{user_id}'"
        LOGGER.info(f"Executing SQL: {sql}")
       
        result = redshift_data.execute_statement(
            WorkgroupName=WORKGROUP_NAME,
            Database=DATABASE,
            SecretArn=SECRET_ARN,
            Sql=sql
        )
       
        statement_id = result['Id']
        import time
        while True:
            result = redshift_data.describe_statement(Id=statement_id)
            if result['Status'] in ['FINISHED', 'FAILED', 'ABORTED']:
                break
            time.sleep(0.5)
       
        if result['Status'] != 'FINISHED':
            LOGGER.error(f"Redshift query failed: {result['Status']}")
            return {}
       
        records = redshift_data.get_statement_result(Id=statement_id)
        LOGGER.info(f"Retrieved {len(records.get('Records', []))} records")
       
        severity_map = {}
        for record in records.get('Records', []):
            run_id = record[0].get('stringValue', '')
            severity = record[1].get('stringValue', '')
            if run_id and severity:
                severity_map[run_id] = severity
       
        return severity_map
    except Exception as e:
        LOGGER.error(f"Error getting severities by user: {str(e)}")
        return {}
 
def get_documents_by_user(user_id):
    try:
        response = user_docs.scan(
            FilterExpression=Attr('user_doc_id').begins_with(f"{user_id}:")
        )
        items = response.get('Items', [])
       
        while 'LastEvaluatedKey' in response:
            response = user_docs.scan(
                FilterExpression=Attr('user_doc_id').begins_with(f"{user_id}:"),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))
       
        severity_map = get_severities_by_user(user_id)
        LOGGER.info(f"Severity map for user {user_id}: {severity_map}")
       
        result = []
        for doc in items:
            state = doc.get('state')
            run_id = doc.get('run_id')
           
            if str(state) == '4':
                severity = severity_map.get(run_id, 'running')
                LOGGER.info(f"Doc with run_id {run_id}, state {state}: severity = {severity}")
            else:
                severity = 'running'
           
            result.append(transform_document(doc, exclude_user_id=True, severity=severity))
       
        return result
    except Exception as e:
        LOGGER.error(f"Error retrieving documents for user {user_id}: {str(e)}")
        raise
 
def get_findings_by_doc_ids(doc_ids):
    try:
        findings_map = {}
        for doc_id in doc_ids:
            try:
                response = findings_table.scan(
                    FilterExpression=Attr('doc_id').eq(doc_id)
                )
                items = response.get('Items', [])
                if items:
                    # Get the most recent finding (latest timestamp)
                    latest_item = max(items, key=lambda x: x.get('timestamp', ''))
                    findings_map[doc_id] = latest_item.get('findings', [])
            except Exception as e:
                LOGGER.warning(f"Error getting findings for doc {doc_id}: {e}")
        return findings_map
    except Exception as e:
        LOGGER.error(f"Error retrieving findings: {str(e)}")
        return {}
 
def get_documents_by_run(run_id):
    try:
        response = user_docs.scan(
            FilterExpression=Attr('run_id').eq(run_id)
        )
        items = response.get('Items', [])
       
        while 'LastEvaluatedKey' in response:
            response = user_docs.scan(
                FilterExpression=Attr('run_id').eq(run_id),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))
       
        # Get doc_ids and fetch findings
        doc_ids = []
        for doc in items:
            user_doc_id = doc.get('user_doc_id', '')
            if ':' in user_doc_id:
                doc_id = user_doc_id.split(':', 1)[1]
                doc_ids.append(doc_id)
       
        findings_map = get_findings_by_doc_ids(doc_ids)
       
        # Transform documents with findings
        result = []
        for doc in items:
            user_doc_id = doc.get('user_doc_id', '')
            doc_id = user_doc_id.split(':', 1)[1] if ':' in user_doc_id else ''
            findings = findings_map.get(doc_id, [])
            result.append(transform_document(doc, exclude_run_id=True, findings=findings))
       
        return result
    except Exception as e:
        LOGGER.error(f"Error retrieving documents for run {run_id}: {str(e)}")
        raise
 
def get_dashboard_stats(user_id=None):
    try:
        if user_id:
            response = user_docs.scan(
                FilterExpression=Attr('user_doc_id').begins_with(f"{user_id}:")
            )
        else:
            response = user_docs.scan()
        items = response.get('Items', [])
       
        while 'LastEvaluatedKey' in response:
            if user_id:
                response = user_docs.scan(
                    FilterExpression=Attr('user_doc_id').begins_with(f"{user_id}:"),
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
            else:
                response = user_docs.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            items.extend(response.get('Items', []))
       
        total_documents = len(items)
        completed_documents = sum(1 for doc in items if str(doc.get('state')) == '4')
        in_progress_documents = total_documents - completed_documents
       
        from datetime import timezone
        now = datetime.now(timezone.utc)
        current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        reviews_per_month = 0
       
        for doc in items:
            if str(doc.get('state')) == '4':
                timestamp_str = doc.get('timestamp', '')
                if timestamp_str:
                    try:
                        if timestamp_str.endswith('Z'):
                            doc_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        else:
                            doc_time = datetime.fromisoformat(timestamp_str).replace(tzinfo=timezone.utc)
                       
                        if doc_time >= current_month_start:
                            reviews_per_month += 1
                    except Exception as e:
                        LOGGER.warning(f"Failed to parse timestamp {timestamp_str}: {e}")
                        continue
       
        risk_distribution = get_risk_distribution(user_id)
       
        stats = {
            'total_documents': total_documents,
            'completed_documents': completed_documents,
            'in_progress_documents': in_progress_documents,
            'reviews_per_month': reviews_per_month,
            'risk_distribution': risk_distribution
        }
       
        if user_id:
            stats['user_id'] = user_id
           
        return stats
    except Exception as e:
        LOGGER.error(f"Error retrieving dashboard stats: {str(e)}")
        raise
 
def handle_dashboard(user_id=None):
    try:
        stats = get_dashboard_stats(user_id)
        return response(200, {'kpi': stats})
    except Exception as e:
        LOGGER.error(f"Error in handle_dashboard: {str(e)}")
        return response(500, {'error': 'Internal server error'})
 
def get_date_ranges():
    from datetime import timezone
    now = datetime.now(timezone.utc)
    current_day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    current_day_end = current_day_start + timedelta(days=1)
    last_day_start = current_day_start - timedelta(days=1)
   
    current_week_start = current_day_start - timedelta(days=current_day_start.weekday())
    current_week_end = current_week_start + timedelta(days=7)
    last_week_start = current_week_start - timedelta(days=7)
    last_week_end = current_week_start
   
    return {
        'current_day_start': current_day_start,
        'current_day_end': current_day_end,
        'last_day_start': last_day_start,
        'last_day_end': current_day_start,
        'current_week_start': current_week_start,
        'current_week_end': current_week_end,
        'last_week_start': last_week_start,
        'last_week_end': last_week_end
    }
 
def calculate_percentage_increase(current, previous):
    if previous == 0:
        return 0.0
    return round(((current - previous) / previous) * 100, 2)
 
def get_documents_uploaded_by_day(user_id, day_start, day_end):
    try:
        if user_id:
            response = user_docs.scan(
                FilterExpression=Attr('user_doc_id').begins_with(f"{user_id}:") & Attr('timestamp').between(day_start.isoformat(), day_end.isoformat())
            )
        else:
            response = user_docs.scan(
                FilterExpression=Attr('timestamp').between(day_start.isoformat(), day_end.isoformat())
            )
        items = response.get('Items', [])
       
        while 'LastEvaluatedKey' in response:
            if user_id:
                response = user_docs.scan(
                    FilterExpression=Attr('user_doc_id').begins_with(f"{user_id}:") & Attr('timestamp').between(day_start.isoformat(), day_end.isoformat()),
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
            else:
                response = user_docs.scan(
                    FilterExpression=Attr('timestamp').between(day_start.isoformat(), day_end.isoformat()),
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
            items.extend(response.get('Items', []))
       
        return len(items)
    except Exception as e:
        LOGGER.error(f"Error getting documents uploaded by day: {str(e)}")
        return 0
 
def get_in_progress_by_week(user_id, week_start, week_end):
    try:
        if user_id:
            response = user_docs.scan(
                FilterExpression=Attr('user_doc_id').begins_with(f"{user_id}:") & Attr('state').ne(4) & Attr('timestamp').between(week_start.isoformat(), week_end.isoformat())
            )
        else:
            response = user_docs.scan(
                FilterExpression=Attr('state').ne(4) & Attr('timestamp').between(week_start.isoformat(), week_end.isoformat())
            )
        items = response.get('Items', [])
       
        while 'LastEvaluatedKey' in response:
            if user_id:
                response = user_docs.scan(
                    FilterExpression=Attr('user_doc_id').begins_with(f"{user_id}:") & Attr('state').ne(4) & Attr('timestamp').between(week_start.isoformat(), week_end.isoformat()),
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
            else:
                response = user_docs.scan(
                    FilterExpression=Attr('state').ne(4) & Attr('timestamp').between(week_start.isoformat(), week_end.isoformat()),
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
            items.extend(response.get('Items', []))
       
        return len(items)
    except Exception as e:
        LOGGER.error(f"Error getting in-progress documents by week: {str(e)}")
        return 0
 
def get_risks_by_week(user_id, week_start, week_end):
    try:
        user_filter = f"AND user_id = '{user_id}'" if user_id else ""
        sql = f"""
            SELECT severity, COUNT(*) as count
            FROM mart_findings
            WHERE severity IN ('CRITICAL', 'HIGH')
            AND timestamp >= '{week_start.isoformat()}'
            AND timestamp < '{week_end.isoformat()}'
            {user_filter}
            GROUP BY severity
        """
       
        result = redshift_data.execute_statement(
            WorkgroupName=WORKGROUP_NAME,
            Database=DATABASE,
            SecretArn=SECRET_ARN,
            Sql=sql
        )
       
        statement_id = result['Id']
        import time
        while True:
            result = redshift_data.describe_statement(Id=statement_id)
            if result['Status'] in ['FINISHED', 'FAILED', 'ABORTED']:
                break
            time.sleep(0.5)
       
        if result['Status'] != 'FINISHED':
            LOGGER.error(f"Redshift query failed: {result['Status']}")
            return {'CRITICAL': 0, 'HIGH': 0}
       
        records = redshift_data.get_statement_result(Id=statement_id)
        risks = {'CRITICAL': 0, 'HIGH': 0}
       
        for record in records.get('Records', []):
            severity = record[0]['stringValue']
            count = int(record[1]['longValue'])
            if severity in risks:
                risks[severity] = count
       
        return risks
    except Exception as e:
        LOGGER.error(f"Error getting risks by week: {str(e)}")
        return {'CRITICAL': 0, 'HIGH': 0}
 
def get_risk_distribution(user_id=None):
    try:
        user_filter = f"AND user_id = '{user_id}'" if user_id else ""
        sql = f"""
            SELECT severity, COUNT(*) as count
            FROM mart_findings
            WHERE severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')
            {user_filter}
            GROUP BY severity
        """
       
        result = redshift_data.execute_statement(
            WorkgroupName=WORKGROUP_NAME,
            Database=DATABASE,
            SecretArn=SECRET_ARN,
            Sql=sql
        )
       
        statement_id = result['Id']
        import time
        while True:
            result = redshift_data.describe_statement(Id=statement_id)
            if result['Status'] in ['FINISHED', 'FAILED', 'ABORTED']:
                break
            time.sleep(0.5)
       
        if result['Status'] != 'FINISHED':
            LOGGER.error(f"Redshift query failed: {result['Status']}")
            return {'critical': {'count': 0, 'percentage': 0.0}, 'high': {'count': 0, 'percentage': 0.0}, 'medium': {'count': 0, 'percentage': 0.0}, 'low': {'count': 0, 'percentage': 0.0}}
       
        records = redshift_data.get_statement_result(Id=statement_id)
        risks = {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
       
        for record in records.get('Records', []):
            severity = record[0]['stringValue']
            count = int(record[1]['longValue'])
            if severity in risks:
                risks[severity] = count
       
        total = sum(risks.values())
        distribution = {}
        for severity, count in risks.items():
            percentage = round((count / total * 100), 2) if total > 0 else 0.0
            distribution[severity.lower()] = {'count': count, 'percentage': percentage}
       
        return distribution
    except Exception as e:
        LOGGER.error(f"Error getting risk distribution: {str(e)}")
        return {'critical': {'count': 0, 'percentage': 0.0}, 'high': {'count': 0, 'percentage': 0.0}, 'medium': {'count': 0, 'percentage': 0.0}, 'low': {'count': 0, 'percentage': 0.0}}
 
def get_weekly_comparison_stats(user_id=None):
    try:
        ranges = get_date_ranges()
       
        current_day_docs = get_documents_uploaded_by_day(user_id, ranges['current_day_start'], ranges['current_day_end'])
        last_day_docs = get_documents_uploaded_by_day(user_id, ranges['last_day_start'], ranges['last_day_end'])
       
        current_week_in_progress = get_in_progress_by_week(user_id, ranges['current_week_start'], ranges['current_week_end'])
        last_week_in_progress = get_in_progress_by_week(user_id, ranges['last_week_start'], ranges['last_week_end'])
       
        current_week_risks = get_risks_by_week(user_id, ranges['current_week_start'], ranges['current_week_end'])
        last_week_risks = get_risks_by_week(user_id, ranges['last_week_start'], ranges['last_week_end'])
       
        stats = {
            'daily': {
                'current_day': {'documents_uploaded': current_day_docs},
                'last_day': {'documents_uploaded': last_day_docs},
                'comparison': {
                    'documents_uploaded_increase': current_day_docs - last_day_docs,
                    'documents_uploaded_percentage_increase': calculate_percentage_increase(current_day_docs, last_day_docs)
                }
            },
            'weekly': {
                'current_week': {
                    'in_progress_documents': current_week_in_progress,
                    'critical_risks': current_week_risks['CRITICAL'],
                    'high_risks': current_week_risks['HIGH']
                },
                'last_week': {
                    'in_progress_documents': last_week_in_progress,
                    'critical_risks': last_week_risks['CRITICAL'],
                    'high_risks': last_week_risks['HIGH']
                },
                'comparison': {
                    'in_progress_increase': current_week_in_progress - last_week_in_progress,
                    'in_progress_percentage_increase': calculate_percentage_increase(current_week_in_progress, last_week_in_progress),
                    'critical_risks_increase': current_week_risks['CRITICAL'] - last_week_risks['CRITICAL'],
                    'critical_risks_percentage_increase': calculate_percentage_increase(current_week_risks['CRITICAL'], last_week_risks['CRITICAL']),
                    'high_risks_increase': current_week_risks['HIGH'] - last_week_risks['HIGH'],
                    'high_risks_percentage_increase': calculate_percentage_increase(current_week_risks['HIGH'], last_week_risks['HIGH'])
                }
            }
        }
       
        if user_id:
            stats['user_id'] = user_id
       
        return stats
    except Exception as e:
        LOGGER.error(f"Error retrieving weekly comparison stats: {str(e)}")
        raise
 
def handle_weekly_comparison(user_id=None):
    try:
        stats = get_weekly_comparison_stats(user_id)
        return response(200, {'kpi': stats})
    except Exception as e:
        LOGGER.error(f"Error in handle_weekly_comparison: {str(e)}")
        return response(500, {'error': 'Internal server error'})
 
def handle_get_documents_by_user(user_id):
    try:
        documents = get_documents_by_user(user_id)
        return response(200, {
            'documents': documents,
            'count': len(documents),
            'user_id': user_id
        })
    except Exception as e:
        LOGGER.error(f"Error in handle_get_documents_by_user: {str(e)}")
        return response(500, {'error': 'Internal server error'})
 
def handle_get_documents_by_run(run_id):
    try:
        documents = get_documents_by_run(run_id)
        return response(200, {
            'documents': documents,
            'run_id': run_id
        })
    except Exception as e:
        LOGGER.error(f"Error in handle_get_documents_by_run: {str(e)}")
        return response(500, {'error': 'Internal server error'})
 
def get_finding_by_run(run_id):
    try:
        sql = f"""
            SELECT doc_id, severity, heading, user_id, run_id, recommendation, findings, timestamp
            FROM mart_findings
            WHERE run_id = '{run_id}'
            LIMIT 1
        """
       
        result = redshift_data.execute_statement(
            WorkgroupName=WORKGROUP_NAME,
            Database=DATABASE,
            SecretArn=SECRET_ARN,
            Sql=sql
        )
       
        statement_id = result['Id']
        import time
        while True:
            result = redshift_data.describe_statement(Id=statement_id)
            if result['Status'] in ['FINISHED', 'FAILED', 'ABORTED']:
                break
            time.sleep(0.5)
       
        if result['Status'] != 'FINISHED':
            LOGGER.error(f"Redshift query failed: {result['Status']}")
            return None
       
        records = redshift_data.get_statement_result(Id=statement_id)
       
        if not records.get('Records'):
            return None
       
        record = records['Records'][0]
        finding = {
            'doc_id': record[0].get('stringValue', ''),
            'severity': record[1].get('stringValue', ''),
            'heading': record[2].get('stringValue', ''),
            'user_id': record[3].get('stringValue', ''),
            'run_id': record[4].get('stringValue', ''),
            'recommendation': record[5].get('stringValue', ''),
            'findings': record[6].get('stringValue', ''),
            'timestamp': record[7].get('stringValue', '')
        }
       
        return finding
    except Exception as e:
        LOGGER.error(f"Error getting finding by run: {str(e)}")
        return None
 
def handle_risk_assessment(run_id):
    try:
        finding = get_finding_by_run(run_id)
        if finding:
            return response(200, finding)
        else:
            return response(404, {'error': f'No finding found for run_id: {run_id}'})
    except Exception as e:
        LOGGER.error(f"Error in handle_risk_assessment: {str(e)}")
        return response(500, {'error': 'Internal server error'})