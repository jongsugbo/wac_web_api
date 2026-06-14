import pymysql.cursors  
import boto3, botocore
import os
from botocore.exceptions import ClientError

import logging

from config import settings

# Configure logging to write to a file
logging.basicConfig(
    level=logging.INFO,
    filename="app.log",
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

#--- for WAC database connection ---#
def getConnection():
     
    connection = pymysql.connect(host=settings.db_host,
                                 port=settings.db_port,
                                 user=settings.db_user,
                                 password=settings.db_password,
                                 db=settings.db_name,
                                 cursorclass=pymysql.cursors.DictCursor)
    return connection


#--- for S3 Bucket connection ---#    
def getS3Connection():
     
    connection = boto3.client("s3",
                                aws_access_key_id=settings.aws_access_key_id,
                                aws_secret_access_key=settings.aws_secret_access_key,
                                region_name=settings.aws_region
                                )
    return connection

#aws_access_key_id='AKIATJHQEGEIEW5LXTUM',
#aws_secret_access_key='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',

#--- for Amazon Textract connection
def getTextractConnection():
    return boto3.client(
        "textract",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key
    )

'''
def getTextractConnection():
    logger.info("connecting...")

    textract = boto3.client(
        "textract",
        region_name="ap-southeast-1",
        aws_access_key_id="AKIATJHQEGEIBXTR7BC3",
        aws_secret_access_key="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",
    )

    logger.info("textract client created: %s", textract)

    # OPTIONAL: smoke test (it will throw ValidationException, that's fine)
    try:
        textract.get_document_analysis(JobId="00000000-0000-0000-0000-000000000000")
    except ClientError as e:
        logger.info("Textract smoke test (expected) error_code=%s message=%s",
                    e.response["Error"].get("Code"),
                    e.response["Error"].get("Message"))

    return textract
'''

# --- For Amazon Bedrock connection --- #
def getBedrockConnection():
    session = boto3.Session(
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_bedrock_region
    )
    return session.client('bedrock-runtime')