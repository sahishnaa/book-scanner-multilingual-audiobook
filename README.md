# Book Scanner to Multilingual Audiobook Converter (AWS)
## Overview
Serverless cloud-based system that converts scanned books, PDFs, and images into multilingual audiobooks using AWS services.

The system automatically performs:
- OCR text extraction
- Language translation
- Text-to-speech synthesis
- Audio storage and playback

## Technologies Used
- AWS S3
- AWS Lambda
- AWS Textract
- AWS Translate
- AWS Polly
- AWS API Gateway
- DynamoDB
- HTML, JavaScript

## Architecture Workflow
1. User uploads a document via the web interface.
2. File is uploaded to S3 using a presigned URL.
3. S3 event triggers the processing Lambda.
4. Textract extracts text.
5. Translate converts text to target language.
6. Polly generates speech audio.
7. MP3 file is stored in S3 for playback.

## Supported Input Formats
- PDF
- JPEG / PNG
- TXT
- RTF (basic support)

## Supported Languages
- English
- Hindi
- German
- Spanish
- French
- Tamil (partial)

## Folder Structure
- frontend/ -> Web interface
- backend/ -> AWS Lambda functions


## How to Deploy
Backend Lambdas and S3 buckets must be created manually in AWS Console.
source code included in this repository. 
