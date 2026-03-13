import json
          import os
          import boto3

          s3 = boto3.client("s3")
          brt = boto3.client("bedrock-agent-runtime")

          BUCKET = os.environ["BUCKET_NAME"]
          KB_ID = os.environ["KNOWLEDGE_BASE_ID"]

          def lambda_handler(event, context):
              """
              Basic flow:
              - Read inputKey from S3
              - Do a simple transformation (upper-case)
              - Write to outputKey in same bucket
              - Call Bedrock Knowledge Base Retrieve with 'query'
              """
              input_key = event.get("inputKey", "input/sample.txt")
              output_key = event.get("outputKey", "output/transformed.txt")
              query = event.get("query", "Summarize the content")

              # 1) Read from S3
              obj = s3.get_object(Bucket=BUCKET, Key=input_key)
              content = obj["Body"].read().decode("utf-8", errors="ignore")

              # 2) Simple transformation
              transformed = content.upper()

              # 3) Write back to S3
              s3.put_object(
                  Bucket=BUCKET,
                  Key=output_key,
                  Body=transformed.encode("utf-8"),
                  ContentType="text/plain"
              )

              # 4) Retrieve from Knowledge Base
              retrieve_resp = brt.retrieve(
                  knowledgeBaseId=KB_ID,
                  retrievalQuery={"text": query}
              )

              return {
                  "statusCode": 200,
                  "body": {
                      "bucket": BUCKET,
                      "inputKey": input_key,
                      "outputKey": output_key,
                      "kbId": KB_ID,
                      "retrieve": retrieve_resp
                  }
              }