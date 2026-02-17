#!/usr/bin/env bash
#
# 部署脚本 — 将项目打包为 Azure Functions 可部署目录
#
# 用法:
#   # 1. 构建部署目录
#   bash live/azure_function/deploy.sh build
#
#   # 2. 本地测试 (需要 Azure Functions Core Tools)
#   bash live/azure_function/deploy.sh local
#
#   # 3. 部署到 Azure
#   bash live/azure_function/deploy.sh publish <function-app-name>
#
# 前提:
#   - 安装 Azure Functions Core Tools: npm install -g azure-functions-core-tools@4
#   - 安装 Azure CLI (部署用): az login
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/.azure_deploy"

# ==============================================================
# 构建部署目录
# ==============================================================
build() {
    echo "=== Building deployment package ==="
    echo "Project root: $PROJECT_ROOT"
    echo "Build dir:    $BUILD_DIR"

    # 清理
    rm -rf "$BUILD_DIR"
    mkdir -p "$BUILD_DIR"

    # 复制 Azure Functions 配置文件
    cp "$SCRIPT_DIR/function_app.py" "$BUILD_DIR/"
    cp "$SCRIPT_DIR/host.json" "$BUILD_DIR/"
    cp "$SCRIPT_DIR/requirements.txt" "$BUILD_DIR/"

    # 复制项目模块 (只复制 .py 文件，不复制 __pycache__)
    for module in core data execution storage config notification live; do
        if [ -d "$PROJECT_ROOT/$module" ]; then
            mkdir -p "$BUILD_DIR/$module"
            find "$PROJECT_ROOT/$module" -name "*.py" -not -path "*__pycache__*" | while read f; do
                # 保持相对路径
                rel="${f#$PROJECT_ROOT/}"
                mkdir -p "$BUILD_DIR/$(dirname "$rel")"
                cp "$f" "$BUILD_DIR/$rel"
            done
            echo "  ✓ $module/"
        fi
    done

    # 创建 .funcignore
    cat > "$BUILD_DIR/.funcignore" << 'EOF'
.git*
.vscode/
__pycache__/
*.pyc
local.settings.json
.azure_deploy/
backtest/
tests/
docs/
pine-scripts/
archive/
*.csv
EOF

    echo ""
    echo "=== Build complete ==="
    echo "Files:"
    find "$BUILD_DIR" -name "*.py" -o -name "*.json" -o -name "*.txt" | sort | while read f; do
        echo "  ${f#$BUILD_DIR/}"
    done
}

# ==============================================================
# 本地运行 (func start)
# ==============================================================
local_run() {
    build

    # 复制 local.settings.json (含敏感信息，不入部署包)
    if [ -f "$SCRIPT_DIR/local.settings.json" ]; then
        cp "$SCRIPT_DIR/local.settings.json" "$BUILD_DIR/"
    elif [ -f "$SCRIPT_DIR/local.settings.template.json" ]; then
        echo "⚠️  local.settings.json not found, copying from template"
        cp "$SCRIPT_DIR/local.settings.template.json" "$BUILD_DIR/local.settings.json"
    else
        echo "⚠️  local.settings.json not found, creating template"
        cat > "$BUILD_DIR/local.settings.json" << 'EOF'
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "ACTIVE_PROFILE": "oanda_demo",
    "CFD_DRY_RUN": "true"
  }
}
EOF
    fi

    echo ""
    echo "=== Starting Azure Functions locally ==="
    cd "$BUILD_DIR"
    func start
}

# ==============================================================
# 部署到 Azure
# ==============================================================
publish() {
    local app_name="${1:?Usage: deploy.sh publish <function-app-name>}"

    build

    echo ""
    echo "=== Publishing to Azure Functions: $app_name ==="
    cd "$BUILD_DIR"
    func azure functionapp publish "$app_name" --python
}

# ==============================================================
# 入口
# ==============================================================
case "${1:-help}" in
    build)
        build
        ;;
    local)
        local_run
        ;;
    publish)
        publish "${2:-}"
        ;;
    *)
        echo "Usage: deploy.sh {build|local|publish <app-name>}"
        echo ""
        echo "Commands:"
        echo "  build              Build deployment directory (.azure_deploy/)"
        echo "  local              Build + run locally with func start"
        echo "  publish <app>      Build + deploy to Azure Functions"
        exit 1
        ;;
esac
