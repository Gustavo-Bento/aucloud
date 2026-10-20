import json, boto3, pytest
from moto import mock_aws
from conftest import load, make_table

def sqs_event(*bodies):
    return {"Records": [{"messageId": str(i), "body": json.dumps(b)} for i, b in enumerate(bodies)]}

def setup(monkeypatch):
    ddb = boto3.resource("dynamodb")
    make_table(ddb, "AUC-StickerSync", "id"); make_table(ddb, "AUC-Log", "id")
    monkeypatch.setenv("STICKER_TABLE", "AUC-StickerSync"); monkeypatch.setenv("LOG_TABLE", "AUC-Log")
    return ddb

@mock_aws
def test_sucesso(monkeypatch):
    ddb = setup(monkeypatch); m = load("consumer", "cons_a")
    m.lambda_handler(sqs_event({"file_name":"a","data":{"id":"1","placa":"ABC1234","valor":20.5}}), None)
    assert ddb.Table("AUC-StickerSync").scan()["Count"] == 1
    assert ddb.Table("AUC-Log").scan()["Items"][0]["status"] == "SUCCESS"

@mock_aws
def test_payload_invalido_loga_erro_e_levanta(monkeypatch):
    ddb = setup(monkeypatch); m = load("consumer", "cons_b")
    r = m.lambda_handler(sqs_event({"file_name":"a","data":{"id":"1"}}), None)
    assert r["batchItemFailures"] == [{"itemIdentifier": "0"}]
    assert ddb.Table("AUC-Log").scan()["Items"][0]["status"] == "ERROR"

@mock_aws
def test_lote_parcial_reprocessa_mensagens_boas(monkeypatch):
    """BatchSize=10 sem ReportBatchItemFailures: 1 msg ruim derruba o lote todo."""
    ddb = setup(monkeypatch); m = load("consumer", "cons_c")
    ruim = {"file_name":"r","data":{"id":"1"}}
    boa = {"file_name":"b","data":{"id":"2","placa":"A","valor":1}}
    r = m.lambda_handler(sqs_event(boa, ruim, boa), None)
    assert isinstance(r, dict) and [f["itemIdentifier"] for f in r.get("batchItemFailures", [])] == ["1"], \
        "Lambda levantou exceção: as 3 mensagens voltam à fila (as boas são reprocessadas)"

@mock_aws
def test_mensagem_sem_data_vira_keyerror(monkeypatch):
    ddb = setup(monkeypatch); m = load("consumer", "cons_d")
    r = m.lambda_handler(sqs_event({"file_name":"a"}), None)
    assert r["batchItemFailures"] == [{"itemIdentifier": "0"}]

@mock_aws
def test_log_id_colisao_sobrescreve(monkeypatch):
    """id do log = timestamp; 2 logs no mesmo microssegundo se sobrescrevem."""
    ddb = setup(monkeypatch); m = load("consumer", "cons_e")
    import datetime as dt
    fixed = dt.datetime(2026,10,20,12,0,0,0)
    class FD(dt.datetime):
        @classmethod
        def utcnow(cls): return fixed
    m.datetime = FD
    m.create_log("SUCCESS","a"); m.create_log("ERROR","b")
    assert ddb.Table("AUC-Log").scan()["Count"] == 2

@mock_aws
def test_reentrega_atualiza_registro_semantica_de_sincronismo(monkeypatch):
    """Decisão: mantido o upsert original (sincronismo = última versão vence)."""
    ddb = setup(monkeypatch); m = load("consumer", "cons_f")
    m.lambda_handler(sqs_event({"file_name":"a","data":{"id":"1","placa":"A","valor":1}}), None)
    m.lambda_handler(sqs_event({"file_name":"a","data":{"id":"1","placa":"B","valor":99}}), None)
    t = ddb.Table("AUC-StickerSync")
    assert t.scan()["Count"] == 1 and t.get_item(Key={"id":"1"})["Item"]["placa"] == "B"

@mock_aws
def test_lista_de_registros_no_arquivo(monkeypatch):
    ddb = setup(monkeypatch); m = load("consumer", "cons_g")
    r = m.lambda_handler(sqs_event({"file_name":"a","data":[{"id":"1","placa":"A","valor":1}]}), None)
    assert len(r["batchItemFailures"]) == 1
