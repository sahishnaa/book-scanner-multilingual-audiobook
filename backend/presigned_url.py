import json
import boto3
import os

s3 = boto3.client('s3')
BUCKET = os.environ.get("INPUT_BUCKET", "sahi-book-scans-2025")

def lambda_handler(event, context):
    qs = event.get("queryStringParameters") or {}
    filename = qs.get("filename")
    lang = qs.get("lang", "en")
    # take content type from query; default safe value
    ctype = qs.get("ctype", "application/octet-stream")

    if not filename:
        return _resp(400, {"error": "filename required"})

    # IMPORTANT: sign with the SAME ContentType and metadata
    url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": BUCKET,
            "Key": filename,
            "ContentType": ctype,
            "Metadata": {"target_lang": lang}
        },
        ExpiresIn=300
    )

    return _resp(200, {"upload_url": url})

def _resp(code, body):
    return {
        "statusCode": code,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Methods": "GET,OPTIONS"
        },
        "body": json.dumps(body)
    }
