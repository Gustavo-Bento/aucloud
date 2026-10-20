import json, boto3, pytest
from moto import mock_aws
from conftest import load, make_table

def setup(monkeypatch, tokens=()):
    ddb = boto3.resource("dynamodb")
    make_table(ddb, "AUC-StickerSync", "id"); make_table(ddb, "AUC-TokenAuth", "token")
    monkeypatch.setenv("STICKER_TABLE","AUC-StickerSync"); monkeypatch.setenv("TOKEN_TABLE","AUC-TokenAuth")
    for t in tokens: ddb.Table("AUC-TokenAuth").put_item(Item=t)
    return ddb

def ev(body): return {"body": json.dumps(body) if not isinstance(body, str) else body}

@mock_aws
def test_autoriza_ok(monkeypatch):
    ddb = setup(monkeypatch, [{"token":"t1","status":"ATIVO"}]); m = load("estacione-api","api_a")
    r = m.lambda_handler(ev({"token":"t1","placa":"ABC1234"}), None)
    assert r["statusCode"] == 200
    assert ddb.Table("AUC-StickerSync").scan()["Count"] == 1

@mock_aws
def test_token_inexistente_401(monkeypatch):
    setup(monkeypatch); m = load("estacione-api","api_b")
    assert m.lambda_handler(ev({"token":"x","placa":"A"}), None)["statusCode"] == 401

@mock_aws
def test_token_inativo_401(monkeypatch):
    setup(monkeypatch,[{"token":"t","status":"INATIVO"}]); m = load("estacione-api","api_c")
    assert m.lambda_handler(ev({"token":"t","placa":"A"}), None)["statusCode"] == 401

@mock_aws
def test_campos_faltando_400(monkeypatch):
    setup(monkeypatch); m = load("estacione-api","api_d")
    assert m.lambda_handler(ev({"token":"t"}), None)["statusCode"] == 400

@mock_aws
def test_json_invalido_400(monkeypatch):
    setup(monkeypatch); m = load("estacione-api","api_e")
    assert m.lambda_handler(ev("{nao json"), None)["statusCode"] == 400

@mock_aws
def test_body_null_deveria_ser_400(monkeypatch):
    """API Gateway proxy envia body=None quando não há corpo."""
    setup(monkeypatch); m = load("estacione-api","api_f")
    r = m.lambda_handler({"body": None}, None)
    assert r["statusCode"] == 400, f"retornou {r['statusCode']}"

@mock_aws
def test_token_sem_campo_status_deveria_ser_401(monkeypatch):
    setup(monkeypatch,[{"token":"t"}]); m = load("estacione-api","api_g")
    r = m.lambda_handler(ev({"token":"t","placa":"A"}), None)
    assert r["statusCode"] == 401, f"retornou {r['statusCode']}"

@mock_aws
def test_body_json_nao_objeto(monkeypatch):
    setup(monkeypatch); m = load("estacione-api","api_h")
    r = m.lambda_handler(ev([1,2]), None)
    assert r["statusCode"] == 400, f"retornou {r['statusCode']}"

@mock_aws
def test_token_nao_string(monkeypatch):
    setup(monkeypatch); m = load("estacione-api","api_i")
    r = m.lambda_handler(ev({"token":123,"placa":"A"}), None)
    assert r["statusCode"] in (400,401), f"retornou {r['statusCode']}"

@mock_aws
def test_ids_unicos_concorrentes(monkeypatch):
    setup(monkeypatch,[{"token":"t","status":"ATIVO"}]); m = load("estacione-api","api_j")
    ids = {m.generate_id() for _ in range(2000)}
    assert len(ids) == 2000, f"colisões: {2000-len(ids)}"

@mock_aws
def test_token_gravado_em_texto_puro(monkeypatch):
    ddb = setup(monkeypatch,[{"token":"segredo","status":"ATIVO"}]); m = load("estacione-api","api_k")
    m.lambda_handler(ev({"token":"segredo","placa":"A"}), None)
    item = ddb.Table("AUC-StickerSync").scan()["Items"][0]
    assert "token" not in item, "token (credencial) persistido em texto puro no StickerSync"
