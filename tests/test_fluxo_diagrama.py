"""Fluxo ponta a ponta do diagrama (S3 -> SyncS3 -> SQS -> Consumer -> DynamoDB) e API de autorização."""
import json, boto3
from moto import mock_aws
from conftest import load, make_table

BUCKET = "sincronismoaws"

@mock_aws
def test_fluxo_sincronismo_completo(monkeypatch):
    ddb = boto3.resource("dynamodb"); make_table(ddb, "AUC-StickerSync", "id"); make_table(ddb, "AUC-Log", "id")
    sqs = boto3.client("sqs"); url = sqs.create_queue(QueueName="UAC-StickerLoad")["QueueUrl"]
    monkeypatch.setenv("QUEUE_URL", url); monkeypatch.setenv("STICKER_TABLE", "AUC-StickerSync"); monkeypatch.setenv("LOG_TABLE", "AUC-Log")
    s3 = boto3.client("s3"); s3.create_bucket(Bucket=BUCKET)
    # equivalente a: aws s3 sync /app/Arquivos/AWS s3://sincronismoaws/estacione
    s3.put_object(Bucket=BUCKET, Key="estacione/ok.json", Body=json.dumps({"id": "1", "placa": "ABC1234", "valor": 20.5}))
    s3.put_object(Bucket=BUCKET, Key="estacione/invalido.json", Body=json.dumps({"id": "2"}))

    sync = load("syncs3", "flow_sync"); cons = load("consumer", "flow_cons")
    for k in ("estacione/ok.json", "estacione/invalido.json"):
        sync.lambda_handler({"Records": [{"s3": {"bucket": {"name": BUCKET}, "object": {"key": k}}}]}, None)

    msgs = sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10)["Messages"]
    assert len(msgs) == 2
    r = cons.lambda_handler({"Records": [{"messageId": m["MessageId"], "body": m["Body"]} for m in msgs]}, None)

    assert len(r["batchItemFailures"]) == 1                                    # só o inválido iria à AUC-Erros
    assert ddb.Table("AUC-StickerSync").get_item(Key={"id": "1"})["Item"]["placa"] == "ABC1234"
    status = sorted(i["status"] for i in ddb.Table("AUC-Log").scan()["Items"])
    assert status == ["ERROR", "SUCCESS"]                                      # grava log (AUC-Log)

@mock_aws
def test_fluxo_autorizacao_completo(monkeypatch):
    ddb = boto3.resource("dynamodb"); make_table(ddb, "AUC-StickerSync", "id"); make_table(ddb, "AUC-TokenAuth", "token")
    monkeypatch.setenv("STICKER_TABLE", "AUC-StickerSync"); monkeypatch.setenv("TOKEN_TABLE", "AUC-TokenAuth")
    ddb.Table("AUC-TokenAuth").put_item(Item={"token": "tk", "status": "ATIVO"})
    api = load("estacione-api", "flow_api")
    r = api.lambda_handler({"body": json.dumps({"token": "tk", "placa": "ABC1234"})}, None)
    assert r["statusCode"] == 200
    item = ddb.Table("AUC-StickerSync").get_item(Key={"id": json.loads(r["body"])["id"]})["Item"]
    assert item["placa"] == "ABC1234" and item["status"] == "AUTHORIZED" and "token" not in item
