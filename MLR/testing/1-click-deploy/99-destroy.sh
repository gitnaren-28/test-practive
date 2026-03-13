#!/usr/bin/env bash
set -euo pipefail

#######

USE_CASE="mlr"
REGION="us-east-2"

###############

STACK_FILE="${USE_CASE}-all-stacks.txt"


if [[ ! -f "$STACK_FILE" ]]; then
  echo "File not found: $STACK_FILE" >&2
  exit 1
fi

# Read stacks into array and reverse order
mapfile -t STACKS < "$STACK_FILE"

# Delete in reverse order (last deployed first)
for ((i=${#STACKS[@]}-1; i>=0; i--)); do
  STACK_NAME="${STACKS[i]}"
  
  # skip empty lines and comments
  [[ -z "$STACK_NAME" || "$STACK_NAME" =~ ^# ]] && continue

  echo "🛑 Deleting stack: $STACK_NAME"

  if ! aws cloudformation delete-stack \
    --stack-name "$STACK_NAME" \
    --region "$REGION"; then
      echo "❌ Failed to start deletion: $STACK_NAME" >&2
      continue
  fi

  echo "⏳ Waiting for deletion: $STACK_NAME..."
  if ! aws cloudformation wait stack-delete-complete \
    --stack-name "$STACK_NAME" \
    --region "$REGION"; then
      echo "❌ Deletion failed or stuck: $STACK_NAME" >&2
      continue
  fi

  echo "✔️ Deleted: $STACK_NAME"
done
