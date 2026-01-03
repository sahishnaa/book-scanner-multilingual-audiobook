import os
import json
import time
import datetime
import uuid
import re
import io
import boto3

s3 = boto3.client('s3')
textract = boto3.client('textract')
translate = boto3.client('translate')
polly = boto3.client('polly')
dynamodb = boto3.resource('dynamodb')

TABLE_NAME = 'BookProcessingRecords'
INPUT_BUCKET = 'sahi-book-scans-2025'
TEXT_BUCKET = 'sahi-extracted-text-2025'
OUTPUT_BUCKET = 'sahi-audiobooks-2025'

table = dynamodb.Table(TABLE_NAME)

TEXT_EXTS = ['.txt', '.rtf']
DOC_EXTS = ['.pdf']
TRANSLATE_CHAR_LIMIT = 4500
POLLY_TEXT_LIMIT = 3000


def lambda_handler(event, context):
    print("Event:", json.dumps(event))
    record = event['Records'][0]
    bucket = record['s3']['bucket']['name']
    key = record['s3']['object']['key']
    job_id = str(uuid.uuid4())
    created_at = datetime.datetime.utcnow().isoformat()

    try:
        head = s3.head_object(Bucket=bucket, Key=key)
        target_lang = head.get('Metadata', {}).get('target_lang', 'en')
    except Exception:
        target_lang = 'en'

    table.put_item(Item={
        'id': job_id,
        'file_key': key,
        'status': 'processing',
        'target_lang': target_lang,
        'created_at': created_at
    })

    try:
        _, ext = os.path.splitext(key.lower())

        if ext in TEXT_EXTS:
            text = extract_text_simple(bucket, key, ext)
        elif ext in DOC_EXTS or ext in ['.jpg', '.jpeg', '.png']:
            text = extract_with_textract(bucket, key)
        else:
            raise Exception(f"Unsupported file type: {ext}")

        if not text.strip():
            raise Exception("No text extracted")

        translated = translate_long_text(text, target_lang)

        audio_key = key.rsplit('.', 1)[0] + f"_{target_lang}.mp3"
        audio_bytes = synthesize_long_text_to_mp3(translated, target_lang)

        s3.put_object(
            Bucket=OUTPUT_BUCKET,
            Key=audio_key,
            Body=audio_bytes,
            ContentType='audio/mpeg'
        )
        s3.put_object(
            Bucket=TEXT_BUCKET,
            Key=f"extracted/{key}_extracted.txt",
            Body=text.encode('utf-8')
        )
        s3.put_object(
            Bucket=TEXT_BUCKET,
            Key=f"translated/{key}_{target_lang}_translated.txt",
            Body=translated.encode('utf-8')
        )

        table.update_item(
            Key={'id': job_id},
            UpdateExpression="set #s=:s, audio_key=:a",
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={':s': 'done', ':a': audio_key}
        )

        return {
            'statusCode': 200,
            'body': json.dumps({'job_id': job_id, 'audio_key': audio_key})
        }

    except Exception as e:
        print("Error:", str(e))
        table.update_item(
            Key={'id': job_id},
            UpdateExpression="set #s=:s, error_msg=:m",
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={':s': 'error', ':m': str(e)}
        )
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}


def extract_text_simple(bucket, key, ext):
    local_path = f"/tmp/{os.path.basename(key)}"
    s3.download_file(bucket, key, local_path)

    with open(local_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    if ext == '.rtf':
        raw = content
        raw = re.sub(r'\\[A-Za-z0-9]+\s?', '', raw)
        raw = re.sub(r'\\u-?\d+\??', '', raw)
        raw = raw.replace('{','').replace('}','')
        raw = re.sub(r'\s+', ' ', raw).strip()
        content = raw
        content = content.encode('latin1', errors='ignore').decode('latin1', errors='ignore')
    
    return content.strip()


def extract_with_textract(bucket, key):
    text = ""
    doc_type = key.lower().split('.')[-1]

    if doc_type in ['pdf']:
        job = textract.start_document_text_detection(
            DocumentLocation={'S3Object': {'Bucket': bucket, 'Name': key}}
        )
        job_id = job['JobId']
        max_wait = 60  # seconds
        elapsed = 0

        while elapsed < max_wait:
            resp = textract.get_document_text_detection(JobId=job_id)
            status = resp['JobStatus']
            print("Textract job status:", status)

            if status == 'SUCCEEDED':
                for b in resp['Blocks']:
                    if b.get('BlockType') == 'LINE':
                        text += b.get('Text', '') + " "
                break
            elif status == 'FAILED':
                raise Exception('Textract async job failed')

            time.sleep(2)
            elapsed += 2

        if not text.strip():
            raise Exception("Textract returned no text")

    elif doc_type in ['jpg', 'jpeg', 'png']:
        resp = textract.detect_document_text(
            Document={'S3Object': {'Bucket': bucket, 'Name': key}}
        )
        for block in resp['Blocks']:
            if block['BlockType'] == 'LINE':
                text += block['Text'] + " "

    else:
        raise Exception(f"Unsupported file type: {doc_type}")

    return text.strip()


def chunk_text(text, limit):
    paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
    current = ""

    for p in paragraphs:
        if len(current) + len(p) < limit:
            current += " " + p
        else:
            yield current.strip()
            current = p

    if current:
        yield current.strip()


def translate_long_text(text, target_lang):
    pieces = list(chunk_text(text, TRANSLATE_CHAR_LIMIT))
    translated = []

    for p in pieces:
        resp = translate.translate_text(
            Text=p,
            SourceLanguageCode='auto',
            TargetLanguageCode=target_lang
        )
        translated.append(resp['TranslatedText'])

    return " ".join(translated)


def synthesize_long_text_to_mp3(text, target_lang):
    # language → expressively correct Polly voice mapping
    voice_map = {
        "en": "Joanna",         # English - natural neutral
        "hi": "Aditi",          # Hindi - Indian accent
        "es": "Lucia",          # Spanish - expressive
        "fr": "Celine",         # French - soft warm
        "de": "Vicki",          # German - clear pronunciation
    }

    voice = voice_map.get(target_lang, "Joanna")  # fallback english voice

    audio_bytes = bytearray()
    for piece in chunk_text(text, POLLY_TEXT_LIMIT):
        resp = polly.synthesize_speech(
            Text=piece,
            OutputFormat='mp3',
            VoiceId=voice
        )
        audio_bytes.extend(resp['AudioStream'].read())
    return bytes(audio_bytes)

