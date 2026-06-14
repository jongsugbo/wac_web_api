#API_CONFIG = {
#    "system_a": "https://api.system-a.com/endpoint",
#    "system_b": "https://api.system-b.com/endpoint"
#}

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Asana
    asana_api_token: str
    asana_portfolio_gid: str
    asana_workspace_gid: str
    webhook_url: str

    # Pusher
    pusher_app_id: str
    pusher_key: str
    pusher_secret: str
    pusher_cluster: str = "ap1"

    # Firebase
    firebase_project_id: str
    firebase_service_account_file: str

    # Gmail
    gmail_sender: str
    gmail_app_password: str

    # Database
    db_host: str
    db_port: int = 3306
    db_user: str
    db_password: str
    db_name: str

    # AWS
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str = "ap-southeast-1"
    aws_bedrock_region: str = "us-east-1"

    # App
    org_code: str
    poll_interval: int = 60
    flask_debug: bool = False
    log_level: str = "INFO"
    cors_origins: str = "*"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # AWS SQS
    sqs_region: str = "ap-southeast-1"
    edms_ingestion_queue_url: str

    # S3
    s3_bucket: str = "vivant-wac-uat"

    # Bedrock
    bedrock_model_id: str = "anthropic.claude-3-5-sonnet-20240620-v1:0"

settings = Settings()