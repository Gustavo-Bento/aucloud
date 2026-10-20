import json
import logging
import os
import uuid
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")

TOKEN_TABLE = os.environ["TOKEN_TABLE"]
STICKER_TABLE = os.environ["STICKER_TABLE"]

token_table = dynamodb.Table(TOKEN_TABLE)
sticker_table = dynamodb.Table(STICKER_TABLE)


def lambda_handler(event, context):
    """
    API Gateway Entry Point
    """

    logger.info(
        "Received event: %s",
        json.dumps(event)
    )

    try:

        # API Gateway (proxy) envia "body": null quando não há corpo
        body = json.loads(
            event.get("body") or "{}"
        )

        validate_payload(body)

        token = body["token"]

        validate_token(token)

        authorization = create_authorization(body)

        return response(
            200,
            {
                "message": "Authorization granted",
                "id": authorization["id"]
            }
        )

    except ValueError as ex:

        logger.warning(str(ex))

        return response(
            400,
            {
                "message": str(ex)
            }
        )

    except PermissionError as ex:

        logger.warning(str(ex))

        return response(
            401,
            {
                "message": str(ex)
            }
        )

    except Exception as ex:

        logger.exception(
            "Unexpected error"
        )

        return response(
            500,
            {
                "message": "Internal server error"
            }
        )


def validate_payload(payload):
    """
    Validate request payload.
    """

    if not isinstance(payload, dict):
        raise ValueError(
            "Request body must be a JSON object"
        )

    required_fields = [
        "token",
        "placa"
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

    if not isinstance(payload["token"], str):
        raise ValueError(
            "Field 'token' must be a string"
        )


def validate_token(token):
    """
    Validate token against DynamoDB.
    """

    result = token_table.get_item(
        Key={
            "token": token
        }
    )

    item = result.get("Item")

    if not item:
        raise PermissionError(
            "Token not found"
        )

    if item.get("status") != "ATIVO":
        raise PermissionError(
            "Token inactive"
        )


def create_authorization(payload):
    """
    Persist authorization.
    """

    authorization = {
        "id": generate_id(),
        "placa": payload["placa"],
        "authorized_at": datetime.now(timezone.utc).isoformat(),
        "status": "AUTHORIZED"
    }

    sticker_table.put_item(
        Item=authorization
    )

    logger.info(
        "Authorization created: %s",
        authorization["id"]
    )

    return authorization


def generate_id():
    """
    Generate unique id.
    """

    return (
        datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        + uuid.uuid4().hex[:8]
    )


def response(status_code, body):
    """
    Standard API response.
    """

    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json"
        },
        "body": json.dumps(body)
    }