import importlib.util, os, sys, json
import boto3, pytest
from moto import mock_aws

ROOT = os.path.join(os.path.dirname(__file__), "..", "lambda")

@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    for k, v in {"AWS_ACCESS_KEY_ID": "t", "AWS_SECRET_ACCESS_KEY": "t",
                 "AWS_DEFAULT_REGION": "us-east-1"}.items():
        monkeypatch.setenv(k, v)

def load(name, unique):
    path = os.path.join(ROOT, name, "lambda_function.py")
    spec = importlib.util.spec_from_file_location(unique, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def make_table(ddb, name, key):
    ddb.create_table(TableName=name, BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": key, "AttributeType": "S"}],
        KeySchema=[{"AttributeName": key, "KeyType": "HASH"}])
