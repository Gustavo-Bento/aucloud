import json
import logging
import os
from datetime import datetime
from decimal import Decimal

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")

STICKER_TABLE = os.environ["STICKER_TABLE"]
LOG_TABLE = os.environ["LOG_TABLE"]

sticker_table = dynamodb.Table(STICKER_TABLE)
log_table = dynamodb.Table(LOG_TABLE)


def lambda_handler(event, context):
    """
    SQS Consumer

    Responsável por:
    - Consumir mensagens da fila
    - Validar payload
    - Persistir informações
    - Registrar logs
    """

    logger.info(
        "Received event: %s",
        json.dumps(event)
    )

    for record in event["Records"]:

        try:

            message = json.loads(
                record["body"]
            )

            process_message(message)

        except Exception as ex:

            logger.exception(
                "Error processing message"
            )

            create_log(
                status="ERROR",
                details=str(ex)
            )

            raise ex

    return {
        "statusCode": 200,
        "message": "Messages processed successfully"
    }


def process_message(message: dict):
    """
    Processa a mensagem recebida do SQS.
    """

    payload = message["data"]

    validate_payload(payload)

    save_sticker(payload)

    create_log(
        status="SUCCESS",
        details=f"File processed: {message['file_name']}"
    )


def validate_payload(payload: dict):
    """
    Validação simples do payload.
    """

    required_fields = [
        "id",
        "placa",
        "valor"
    ]

    missing_fields = [
        field
        for field in required_fields
        if field not in payload
    ]

    if missing_fields:

        raise ValueError(
            f"Missing required fields: {missing_fields}"
        )


def save_sticker(payload: dict):
    """
    Persiste dados na tabela AUC-StickerSync.
    """

    sticker_table.put_item(
        Item={
            "id": payload["id"],
            "placa": payload["placa"],
            "valor": Decimal(
                str(payload["valor"])
            ),
            "processed_at": datetime.utcnow().isoformat()
        }
    )

    logger.info(
        "Record saved successfully: %s",
        payload["id"]
    )


def create_log(
    status: str,
    details: str
):
    """
    Registra log operacional.
    """

    timestamp = datetime.utcnow().isoformat()

    log_table.put_item(
        Item={
            "id": timestamp,
            "status": status,
            "details": details,
            "timestamp": timestamp
        }
    )

    logger.info(
        "Log created: %s",
        status
    )