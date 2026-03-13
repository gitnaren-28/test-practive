aws cloudformation create-stack \

  --stack-name demo-glue-crawler-stack \

  --template-body file://glue-crawler-stack.yaml \

  --parameters \

    ParameterKey=GlueDatabaseName,ParameterValue=demo_glue_db \

    ParameterKey=GlueCrawlerName,ParameterValue=demo_json_crawler \

    ParameterKey=S3BucketName,ParameterValue=my-demo-data-bucket \

    ParameterKey=S3DataLocation,ParameterValue=s3://my-demo-data-bucket/json-data/ \

  --capabilities CAPABILITY_NAMED_IAM