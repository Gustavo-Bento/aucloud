import json, boto3, pytest
from moto import mock_aws
from conftest import load

def s3_event(bucket, key):
    return {"Records": [{"s3": {"bucket": {"name": bucket}, "object": {"key": key}}}]}

@mock_aws
def test_json_valido_vai_para_sqs(monkeypatch):
    sqs = boto3.client("sqs"); url = sqs.create_queue(QueueName="UAC-StickerLoad")["QueueUrl"]
    monkeypatch.setenv("QUEUE_URL", url)
    s3 = boto3.client("s3"); s3.create_bucket(Bucket="sincronismoaws-estacione")
    s3.put_object(Bucket="sincronismoaws-estacione", Key="estacione/a.json", Body=json.dumps({"id":"1","placa":"ABC1234","valor":20.5}))
    m = load("syncs3", "syncs3_a")
    r = m.lambda_handler(s3_event("sincronismoaws-estacione", "estacione/a.json"), None)
    assert r["statusCode"] == 200
    msgs = sqs.receive_message(QueueUrl=url).get("Messages", [])
    assert len(msgs) == 1

@mock_aws
@pytest.mark.xfail(reason="PENDENTE: layout do arquivo posicional não foi fornecido; parse atual é JSON", strict=True)
def test_arquivo_posicional_REGRA_DE_NEGOCIO(monkeypatch):
    """O diagrama diz 'Arquivo Posicional' (TXT de largura fixa), não JSON."""
    sqs = boto3.client("sqs"); url = sqs.create_queue(QueueName="UAC-StickerLoad")["QueueUrl"]
    monkeypatch.setenv("QUEUE_URL", url)
    s3 = boto3.client("s3"); s3.create_bucket(Bucket="sincronismoaws-estacione")
    s3.put_object(Bucket="sincronismoaws-estacione", Key="estacione/a.txt", Body=b"0001ABC1234000002050")
    m = load("syncs3", "syncs3_b")
    r = m.lambda_handler(s3_event("sincronismoaws-estacione", "estacione/a.txt"), None)
    assert r["statusCode"] == 200, f"Falhou com arquivo posicional: {r}"

@mock_aws
def test_falha_nao_propaga_excecao_logo_sem_retry_nem_dlq(monkeypatch):
    """Erro vira return 500; Lambda considera sucesso -> evento S3 perdido."""
    sqs = boto3.client("sqs"); url = sqs.create_queue(QueueName="UAC-StickerLoad")["QueueUrl"]
    monkeypatch.setenv("QUEUE_URL", url)
    s3 = boto3.client("s3"); s3.create_bucket(Bucket="sincronismoaws-estacione")
    s3.put_object(Bucket="sincronismoaws-estacione", Key="x", Body=b"nao eh json")
    m = load("syncs3", "syncs3_c")
    try:
        m.lambda_handler(s3_event("sincronismoaws-estacione", "x"), None)
    except Exception:
        return
    raise AssertionError("Exceção engolida: o S3 nunca fará retry/DLQ")

@mock_aws
def test_chave_com_espaco_url_encoded(monkeypatch):
    sqs = boto3.client("sqs"); url = sqs.create_queue(QueueName="UAC-StickerLoad")["QueueUrl"]
    monkeypatch.setenv("QUEUE_URL", url)
    s3 = boto3.client("s3"); s3.create_bucket(Bucket="sincronismoaws-estacione")
    s3.put_object(Bucket="sincronismoaws-estacione", Key="estacione/meu arquivo.json", Body=json.dumps({"id":"1","placa":"A","valor":1}))
    m = load("syncs3", "syncs3_d")
    # S3 real envia 'estacione/meu+arquivo.json'
    r = m.lambda_handler(s3_event("sincronismoaws-estacione", "estacione/meu+arquivo.json"), None)
    assert r["statusCode"] == 200, f"Chave URL-encoded não decodificada: {r}"

@mock_aws
def test_lote_parcial_preserva_registros_bons(monkeypatch):
    sqs = boto3.client("sqs"); url = sqs.create_queue(QueueName="UAC-StickerLoad")["QueueUrl"]
    monkeypatch.setenv("QUEUE_URL", url)
    s3 = boto3.client("s3"); s3.create_bucket(Bucket="sincronismoaws-estacione")
    s3.put_object(Bucket="sincronismoaws-estacione", Key="ruim", Body=b"xx")
    s3.put_object(Bucket="sincronismoaws-estacione", Key="bom", Body=json.dumps({"id":"1","placa":"A","valor":1}))
    m = load("syncs3", "syncs3_e")
    ev = {"Records": s3_event("sincronismoaws-estacione","ruim")["Records"] + s3_event("sincronismoaws-estacione","bom")["Records"]}
    with pytest.raises(RuntimeError):          # falha propagada -> retry do S3
        m.lambda_handler(ev, None)
    n = len(sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10).get("Messages", []))
    assert n == 1                               # o arquivo bom foi enviado mesmo assim

@mock_aws
def test_marcador_de_pasta_ignorado(monkeypatch):
    sqs = boto3.client("sqs"); url = sqs.create_queue(QueueName="UAC-StickerLoad")["QueueUrl"]
    monkeypatch.setenv("QUEUE_URL", url)
    m = load("syncs3", "syncs3_f")
    assert m.lambda_handler(s3_event("sincronismoaws-estacione", "estacione/"), None)["statusCode"] == 200
