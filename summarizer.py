import json
import logging
import os
from dbconnect import getS3Connection, getBedrockConnection, getTextractConnection
import boto3
from botocore.exceptions import ClientError
import time
import random

from config import settings

S3_BUCKET = settings.s3_bucket
BEDROCK_MODEL_ID = settings.bedrock_model_id

# Configure logging to write to a file
logging.basicConfig(
    level=logging.INFO,
    filename="app.log",
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Extract content of the file
def extract_text_from_textract(filename):

    textract = getTextractConnection()

    ext = os.path.splitext(filename.lower())[1]

    # =====================================================
    # ORIGINAL LOGIC (UNCHANGED) — IMAGE FILES
    # =====================================================
    if ext in [".jpg", ".jpeg", ".png"]:
        response = textract.analyze_document(
            Document={'S3Object': {'Bucket': S3_BUCKET, 'Name': filename}},
            FeatureTypes=["FORMS", "TABLES"]
        )

        lines = []
        for block in response["Blocks"]:
            if block["BlockType"] == "LINE":
                lines.append(block["Text"])
        return "\n".join(lines)

    # =====================================================
    # ADDED LOGIC — PDF FILES (ASYNC REQUIRED)
    # =====================================================
    elif ext == ".pdf":
        try:
            start = textract.start_document_analysis(
                DocumentLocation={
                    'S3Object': {
                        'Bucket': S3_BUCKET,
                        'Name': filename
                    }
                },
                FeatureTypes=["FORMS", "TABLES"]
            )

            job_id = start["JobId"]

            blocks = []
            next_token = None

            while True:
                if next_token:
                    response = textract.get_document_analysis(
                        JobId=job_id,
                        NextToken=next_token
                    )
                else:
                    response = textract.get_document_analysis(
                        JobId=job_id
                    )

                status = response["JobStatus"]

                if status == "FAILED":
                    logger.error(f"Textract PDF failed: {filename}")
                    return ""

                if status == "IN_PROGRESS":
                    time.sleep(2)
                    continue

                blocks.extend(response.get("Blocks", []))
                next_token = response.get("NextToken")

                if not next_token:
                    break

            lines = []
            for block in blocks:
                if block["BlockType"] == "LINE":
                    lines.append(block["Text"])

            return "\n".join(lines)

        except ClientError as e:
            logger.error(
                "Textract PDF error %s: %s",
                e.response["Error"].get("Code"),
                e.response["Error"].get("Message")
            )
            return ""

    # =====================================================
    # UNSUPPORTED FILE TYPES
    # =====================================================
    else:
        logger.warning(f"Unsupported file type for Textract: {filename}")
        return ""

# Summarize the content of the file using Claude 3.5 Sonnet
def summarize_text_with_bedrock(text, retries=3, alt_prompt=None):
    bedrock = getBedrockConnection()

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "messages": [
            {
                "role": "user",
                "content": f"Summarize the following document content in clear, professional bullet points:\n\n{text}"
            }
        ],
        "max_tokens": 500,
        "temperature": 0.5
    }

    if alt_prompt is not None and alt_prompt.strip():
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "messages": [
                {
                    "role": "user",
                    "content": f"{alt_prompt}\n\n{text}"
                }
            ],
            "max_tokens": 500,
            "temperature": 0.5
        }

    for attempt in range(retries):
        try:
            response = bedrock.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json"
            )

            response_body = response["body"].read().decode("utf-8")
            result = json.loads(response_body)
            content_blocks = result.get("content", [])

            if isinstance(content_blocks, list):
                return "\n".join(
                    block["text"] for block in content_blocks if block.get("type") == "text"
                ).strip()

            return "[No summary returned] Raw: " + response_body

        except bedrock.exceptions.ThrottlingException:
            wait_time = 2 ** attempt + random.uniform(0, 1)
            time.sleep(wait_time)
        except Exception as e:
            return f"[Error during summarization: {str(e)}]"

    return "[Error: Too many retry attempts due to throttling]"



