import json
import logging
import os
from urllib.parse import unquote_plus

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")
sqs_client = boto3.client("sqs")

QUEUE_URL = os.environ["QUEUE_URL"]


def lambda_handler(event, context):
    """
    Triggered by S3 ObjectCreated events.

    Responsibilities:
    - Read uploaded file from S3
    - Validate file format
    - Send payload to SQS

    Parameters
    ----------
    event : dict
        AWS Lambda event

    context : LambdaContext
        AWS Lambda context

    Returns
    -------
    dict
        Execution result
    """

    logger.info("Received event: %s", json.dumps(event))

    failures = []

    for record in event["Records"]:

        bucket_name = record["s3"]["bucket"]["name"]

        # O S3 envia a chave URL-encoded (espaço -> '+', acentos -> %XX)
        object_key = unquote_plus(record["s3"]["object"]["key"])

        # Marcadores de pasta não possuem conteúdo
        if object_key.endswith("/"):
            logger.info("Skipping folder marker %s", object_key)
            continue

        try:

            logger.info(
                "Processing file %s from bucket %s",
                object_key,
                bucket_name
            )

            file_content = read_file(
                bucket_name,
                object_key
            )

            payload = build_payload(
                object_key,
                file_content
            )

            send_to_queue(payload)

        except Exception:

            # Um arquivo inválido não pode impedir o processamento dos demais
            logger.exception(
                "Error processing file %s",
                object_key
            )

            failures.append(object_key)

    if failures:

        # Propaga a falha: o S3 invoca a Lambda de forma assíncrona e
        # faz retry automático; sem isso o evento seria perdido em silêncio.
        raise RuntimeError(
            f"Failed to process {len(failures)} file(s): {failures}"
        )

    return {
        "statusCode": 200,
        "message": "File processed successfully"
    }


def read_file(bucket_name: str, object_key: str) -> dict:
    """
    Reads JSON file from S3.
    """

    response = s3_client.get_object(
        Bucket=bucket_name,
        Key=object_key
    )

    content = response["Body"].read()

    return json.loads(content)


def build_payload(
    file_name: str,
    content: dict
) -> dict:
    """
    Creates standard payload sent to SQS.
    """

    return {
        "file_name": file_name,
        "data": content
    }


def send_to_queue(payload: dict):
    """
    Sends message to SQS.
    """

    response = sqs_client.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps(payload)
    )

    logger.info(
        "Message sent successfully: %s",
        response["MessageId"]
    )