"""Conformidade do template CloudFormation com o diagrama de regra de negócio."""
import json, os, re, subprocess
import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
T = json.load(open(os.path.join(ROOT, "infra", "cloudformation.json")))
R = T["Resources"]

def of(t): return {k: v for k, v in R.items() if v["Type"] == t}
def code(fn): return open(os.path.join(ROOT, "lambda", fn, "lambda_function.py")).read()

LAMBDAS = {"AUCloud-SyncS3": "syncs3", "AUCloud-Consumer": "consumer", "AUCloud-EstacioneAPI": "estacione-api"}

def test_cfn_lint_limpo():
    r = subprocess.run(["cfn-lint", os.path.join(ROOT, "infra", "cloudformation.json")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout

def test_nomes_dos_recursos_do_diagrama():
    names = lambda t, k: {v["Properties"][k] for v in of(t).values()}
    assert names("AWS::Lambda::Function", "FunctionName") == set(LAMBDAS)
    assert names("AWS::SQS::Queue", "QueueName") == {"UAC-StickerLoad", "AUC-Erros"}
    assert names("AWS::DynamoDB::Table", "TableName") == {"AUC-StickerSync", "AUC-Log", "AUC-TokenAuth"}

@pytest.mark.parametrize("name,folder", LAMBDAS.items())
def test_handler_existe_no_codigo(name, folder):
    props = next(v["Properties"] for v in of("AWS::Lambda::Function").values() if v["Properties"]["FunctionName"] == name)
    module, func = props["Handler"].split(".")
    assert module == "lambda_function" and re.search(rf"^def {func}\(", code(folder), re.M)

@pytest.mark.parametrize("name,folder", LAMBDAS.items())
def test_env_vars_cobrem_o_codigo(name, folder):
    props = next(v["Properties"] for v in of("AWS::Lambda::Function").values() if v["Properties"]["FunctionName"] == name)
    used = set(re.findall(r'os\.environ\["(\w+)"\]', code(folder)))
    assert used <= set(props.get("Environment", {}).get("Variables", {})), used

def test_s3_dispara_syncs3_no_prefixo_estacione():
    b = R["SincronismoBucket"]["Properties"]
    cfg = b["NotificationConfiguration"]["LambdaConfigurations"][0]
    assert cfg["Event"].startswith("s3:ObjectCreated") and cfg["Function"] == {"Fn::GetAtt": ["SyncS3Lambda", "Arn"]}
    assert cfg["Filter"]["S3Key"]["Rules"][0]["Value"] == "estacione/"
    assert b["BucketName"] == {"Ref": "BucketName"} and T["Parameters"]["BucketName"]["Default"] == "sincronismoaws"
    perm = R["SyncS3InvokePermission"]["Properties"]
    assert perm["Principal"] == "s3.amazonaws.com" and R["SincronismoBucket"]["DependsOn"] == "SyncS3InvokePermission"

def test_sqs_consumer_e_dlq():
    q = R["StickerLoadQueue"]["Properties"]
    assert q["RedrivePolicy"]["deadLetterTargetArn"] == {"Fn::GetAtt": ["StickerErrorQueue", "Arn"]}
    esm = R["SQSTriggerConsumer"]["Properties"]
    assert esm["EventSourceArn"] == {"Fn::GetAtt": ["StickerLoadQueue", "Arn"]} and esm["FunctionName"] == {"Ref": "ConsumerLambda"}
    assert "ReportBatchItemFailures" in esm["FunctionResponseTypes"]
    consumer_timeout = R["ConsumerLambda"]["Properties"]["Timeout"]
    assert q["VisibilityTimeout"] >= 6 * consumer_timeout

def test_rota_da_api_e_v1_estacione_autoriza():
    def path(rid):
        r = R[rid]["Properties"]; p = r["PathPart"]; parent = r["ParentId"]
        return (path(parent["Ref"]) if "Ref" in parent else "") + "/" + p
    m = R["ApiGatewayMethod"]["Properties"]
    assert path(m["ResourceId"]["Ref"]) == "/v1/estacione/autoriza" and m["HttpMethod"] == "POST"
    assert m["Integration"]["Type"] == "AWS_PROXY"
    assert "AWS::ApiGateway::Deployment" in {v["Type"] for v in R.values()} and "AWS::ApiGateway::Stage" in {v["Type"] for v in R.values()}
    assert R["ApiInvokePermission"]["Properties"]["Principal"] == "apigateway.amazonaws.com"

def test_iam_cobre_as_chamadas_do_diagrama():
    acts = set()
    for st in R["LambdaExecutionRole"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]:
        acts |= set(st["Action"])
    assert {"s3:GetObject", "sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage",
            "dynamodb:PutItem", "dynamodb:GetItem"} <= acts
    assert not any(a.endswith("*") for a in acts)   # menor privilégio
