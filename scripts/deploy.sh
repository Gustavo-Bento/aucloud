#!/usr/bin/env bash
# Empacota as 3 Lambdas, envia ao bucket de código e cria/atualiza a stack.
# Uso: ./scripts/deploy.sh <bucket-de-codigo> [stack-name] [bucket-sincronismo]
set -euo pipefail

CODE_BUCKET="${1:?Informe o bucket onde os .zip serão enviados}"
STACK="${2:-aucloud-stack}"
SYNC_BUCKET="${3:-sincronismoaws}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"

for fn in syncs3 consumer estacione-api; do
  (cd "$ROOT/lambda/$fn" && zip -qj "$TMP/$fn.zip" lambda_function.py)
  aws s3 cp "$TMP/$fn.zip" "s3://$CODE_BUCKET/aucloud/$fn.zip"
done

aws cloudformation deploy \
  --stack-name "$STACK" \
  --template-file "$ROOT/infra/cloudformation.json" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides CodeBucket="$CODE_BUCKET" BucketName="$SYNC_BUCKET"

# Lambdas já existentes não recarregam o código só por mudar o .zip no S3
for pair in "AUCloud-SyncS3:syncs3" "AUCloud-Consumer:consumer" "AUCloud-EstacioneAPI:estacione-api"; do
  aws lambda update-function-code --function-name "${pair%%:*}" \
    --s3-bucket "$CODE_BUCKET" --s3-key "aucloud/${pair##*:}.zip" >/dev/null
done

aws cloudformation describe-stacks --stack-name "$STACK" \
  --query "Stacks[0].Outputs" --output table
