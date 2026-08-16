#!/bin/zsh

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"
VENV_DIR="$BACKEND_DIR/.venv"
URL="http://127.0.0.1:3002"
API_HEALTH="http://127.0.0.1:8010/api/health"

cd "$PROJECT_DIR"

if curl -fsS "$API_HEALTH" >/dev/null 2>&1 && curl -fsS "$URL" >/dev/null 2>&1; then
  open "$URL"
  exit 0
fi

if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "首次启动：正在准备 Python 环境……"
  python3 -m venv "$VENV_DIR"
fi

if [ ! -f "$VENV_DIR/.dependencies-ready" ] || [ "$BACKEND_DIR/requirements.txt" -nt "$VENV_DIR/.dependencies-ready" ]; then
  echo "正在安装后端依赖……"
  "$VENV_DIR/bin/python" -m pip install --upgrade pip
  "$VENV_DIR/bin/python" -m pip install -r "$BACKEND_DIR/requirements.txt"
  touch "$VENV_DIR/.dependencies-ready"
fi

if [ ! -d "$FRONTEND_DIR/node_modules" ] || [ "$FRONTEND_DIR/package.json" -nt "$FRONTEND_DIR/node_modules" ]; then
  echo "正在安装前端依赖……"
  cd "$FRONTEND_DIR"
  npm install
fi

cleanup() {
  if [ -n "$BACKEND_PID" ]; then kill "$BACKEND_PID" >/dev/null 2>&1 || true; fi
  if [ -n "$FRONTEND_PID" ]; then kill "$FRONTEND_PID" >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT INT TERM

echo "正在启动资产管理……"
cd "$BACKEND_DIR"
PYTHONPYCACHEPREFIX="$BACKEND_DIR/.pycache" "$VENV_DIR/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8010 &
BACKEND_PID=$!

cd "$FRONTEND_DIR"
npm run dev &
FRONTEND_PID=$!

for attempt in {1..60}; do
  if curl -fsS "$API_HEALTH" >/dev/null 2>&1 && curl -fsS "$URL" >/dev/null 2>&1; then
    open "$URL"
    echo "页面已经打开。关闭这个窗口会停止资产管理软件。"
    wait
    exit 0
  fi
  sleep 1
done

echo "启动超时，请查看上方提示。"
exit 1
