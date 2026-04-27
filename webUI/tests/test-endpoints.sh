#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/infiapp-webui-tests.XXXXXX")"
WEBUI_LOG="$TMP_DIR/webui.log"
STORE_RESPONSE="$TMP_DIR/store-response.json"
LIST_RESPONSE="$TMP_DIR/list-response.json"

stop_process_group() {
  local pid="$1"

  if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null; then
    return 0
  fi

  kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
}

cleanup() {
  local exit_code=$?

  stop_process_group "${WEBUI_PID:-}"

  if [[ $exit_code -ne 0 && -f "$WEBUI_LOG" ]]; then
    echo "webUI log:"
    sed -n '1,200p' "$WEBUI_LOG"
  fi

  rm -rf "$TMP_DIR"
  exit "$exit_code"
}

trap cleanup EXIT

assert_contains() {
  local file_path="$1"
  local expected="$2"

  if ! grep -Fq "$expected" "$file_path"; then
    echo "Expected to find '$expected' in $file_path"
    sed -n '1,160p' "$file_path"
    return 1
  fi
}

wait_for_messages_api() {
  for _ in $(seq 1 60); do
    if curl --fail --silent --show-error \
      -X POST \
      -H "content-type: application/json" \
      --data '{"message":"ci smoke"}' \
      "http://127.0.0.1:3000/api/sample/messages" >"$STORE_RESPONSE"; then
      assert_contains "$STORE_RESPONSE" "ci smoke"
      assert_contains "$STORE_RESPONSE" "\"action\":\"store_message\""
      assert_contains "$STORE_RESPONSE" "\"mocked\":true"
      break
    fi

    sleep 1
  done

  if [[ ! -s "$STORE_RESPONSE" ]]; then
    echo "Timed out waiting for /api/sample/messages"
    return 1
  fi

  curl --fail --silent --show-error \
    "http://127.0.0.1:3000/api/sample/messages?limit=5" >"$LIST_RESPONSE"
  assert_contains "$LIST_RESPONSE" "ci smoke"
  assert_contains "$LIST_RESPONSE" "\"action\":\"list_messages\""
}

setsid env \
  INFIAPP_AGENT_BACKEND_MODE=mock \
  NEXT_TELEMETRY_DISABLED=1 \
  npm --prefix "$ROOT_DIR" run start -- -H 127.0.0.1 -p 3000 >"$WEBUI_LOG" 2>&1 &
WEBUI_PID=$!

wait_for_messages_api
