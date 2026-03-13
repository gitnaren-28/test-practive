import json
import boto3
import hashlib
import time
from decimal import Decimal
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key

# =========================
# Config
# =========================
AWS_REGION = "us-east-1"

def get_parameter_value(name: str) -> str:
    ssm = boto3.client("ssm", region_name=AWS_REGION)
    response = ssm.get_parameter(Name=name, WithDecryption=True)
    return response["Parameter"]["Value"]

DDB_TABLE = get_parameter_value("MLR_DDB_TABLE")
SOURCE_BUCKET = get_parameter_value("MLR_S3_USER_BUCKET")
SOURCE_PREFIX = get_parameter_value("MLR_SOURCE_PREFIX")
THRESHOLD = 0.70
SIMHASH_BITS = 64
SHINGLE_K = 3

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")

USER_DOC = get_parameter_value("MLR_USER_DOCUMENTS")

table = dynamodb.Table(USER_DOC)
table_2=dynamodb.Table(DDB_TABLE)

# =========================
# Helpers
# =========================

def generate_timestamp():
    now = datetime.now(timezone.utc)
    return now.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

def normalize(text: str):
    return [l.strip().lower() for l in text.splitlines() if l.strip()]

def chunks(lines, k=SHINGLE_K):
    words = " ".join(lines).split()
    if len(words) < k:
        return {" ".join(words)}
    return {" ".join(words[i:i+k]) for i in range(len(words)-k+1)}

def jaccard(a, b):
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)

def hash_token(token):
    return int(hashlib.md5(token.encode()).hexdigest(), 16)

def simhash(lines, bits=SIMHASH_BITS):
    v = [0] * bits
    for t in " ".join(lines).split():
        h = hash_token(t)
        for i in range(bits):
            v[i] += 1 if h & (1 << i) else -1

    fingerprint = 0
    for i in range(bits):
        if v[i] >= 0:
            fingerprint |= (1 << i)
    return fingerprint

def simhash_similarity(a, b):
    dist = bin(simhash(a) ^ simhash(b)).count("1")
    return 1 - (dist / SIMHASH_BITS)

# =========================
# Diff Lines
# =========================
def modified_lines(old_lines, new_lines):
    start_time=time.perf_counter()
    mods = []
    max_len = max(len(old_lines), len(new_lines))

    for i in range(max_len):
        o = old_lines[i] if i < len(old_lines) else ""
        n = new_lines[i] if i < len(new_lines) else ""
        if o != n:
            mods.append({
                "line_number": i + 1,
                "old": o,
                "new": n
            })

    end_time=time.perf_counter()
    times=end_time-start_time
    print("modifies lines",times)
    return mods

# =========================
# Document Comparison
# =========================

def compare_documents(base_lines, other_lines, existing_doc_id):
    j = jaccard(chunks(base_lines), chunks(other_lines))
    s = simhash_similarity(base_lines, other_lines)

    similarity = (j + s) / 2
    diff = 1 - similarity

    invoke_supervisor = False if diff == 0 else diff <= THRESHOLD

    return {
        "invoke_supervisor": invoke_supervisor,
        "similarity_score": round(similarity, 2),
        "difference_score": round(diff, 2),
        "modified_lines": modified_lines(base_lines, other_lines),
        "most_matching_doc_id": existing_doc_id
    }

# =========================
# Update state
# =========================

def update_state(user_doc_id, timestamp, state_value):
    table_2.update_item(
        Key={
            "user_doc_id": user_doc_id,
            "timestamp": timestamp
        },
        UpdateExpression="SET #st = :s",
        ExpressionAttributeNames={
            "#st": "state"
        },
        ExpressionAttributeValues={
            ":s": state_value
        }
    )

# =========================
# Update matching_doc_id
# =========================

def update_item(user_doc_id, timestamp, most_matching_doc_id):
    table_2.update_item(
        Key={
            "user_doc_id": user_doc_id,
            "timestamp": timestamp
        },
        UpdateExpression="SET most_matching_doc_id = :val",
        ExpressionAttributeValues={
            ":val": most_matching_doc_id
        }
    )


def parse_s3_path(s3_path: str):
    s3_path = s3_path.replace("s3://", "")
    parts = s3_path.split("/", 1)
    bucket = parts[0]
    key = parts[1]
    return bucket, key

# =========================
# Lambda Handler
# =========================

def lambda_handler(event, context):
    try:
        user_id = event["user_id"]
        doc_id = event["doc_id"]
        s3_path = event["s3_path"]
        timestamp=event["timestamp"]
        # Load Base Document
        
        bucket, key = parse_s3_path(s3_path)
        #response = s3.get_object(Bucket=SOURCE_BUCKET, Key=s3_path)
        response = s3.get_object(Bucket=bucket, Key=key)
        base_text = response["Body"].read().decode('utf-8')
        base_lines = normalize(base_text)

        # Query latest record
        response = table.query(
            KeyConditionExpression=Key("user_id").eq(user_id),
            ScanIndexForward=False
        )

        records = response["Items"]
        records = [file for file in records if file['raw_doc_path'] != s3_path]
        best_result = None
        best_score = Decimal("-1")

        if not records:
            return {
                "invoke_supervisor": False,
                "similarity_score": 0,
                "difference_score": 0,
                "modified_lines": [],
                "timestamp": timestamp
            }    

        for file in records:
            file_s3 = file['raw_doc_path']
            existing_user_id = file['user_id']
            existing_doc_id = file['doc_id']

            bucket_existing, key_existing = parse_s3_path(file_s3)
            response = s3.get_object(Bucket=bucket_existing, Key=key_existing)
            existing_file_text = response["Body"].read().decode('utf-8')
            existing_file_lines = normalize(existing_file_text)

            result = compare_documents(base_lines, existing_file_lines, existing_doc_id)
            score = Decimal(str(result["similarity_score"]))
            
            if score > best_score:
                best_score = score
                best_result = result

        
        # Update state and timestamp
        update_state(f"{user_id}:{doc_id}", timestamp, 2)
        best_result.update({"timestamp": timestamp}) if best_result is not None else None

        if best_result['similarity_score'] == 1:
            update_item(f"{user_id}:{doc_id}", timestamp, existing_doc_id)
        return best_result

    except Exception as e:
        raise Exception(f"Lambda failed: {e}")