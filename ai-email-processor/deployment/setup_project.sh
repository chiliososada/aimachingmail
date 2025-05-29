# deployment/setup_project.sh
#!/bin/bash

# プロジェクトセットアップスクリプト

set -e

echo "=== AI Email Processor Setup Script ==="
echo

# カラー定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# プロジェクトルートディレクトリ
PROJECT_ROOT="/opt/ai-email-processor"

# 1. ディレクトリ構造の作成
echo -e "${YELLOW}Creating directory structure...${NC}"
mkdir -p $PROJECT_ROOT/{src,scripts,config,docker,logs,tests,deployment}

# 2. __init__.pyファイルの作成
touch $PROJECT_ROOT/src/__init__.py
touch $PROJECT_ROOT/tests/__init__.py

# 3. 権限設定
echo -e "${YELLOW}Setting permissions...${NC}"
chmod -R 755 $PROJECT_ROOT
chmod +x $PROJECT_ROOT/scripts/*.py 2>/dev/null || true
chmod +x $PROJECT_ROOT/deployment/*.sh 2>/dev/null || true

# 4. Python仮想環境のセットアップ
echo -e "${YELLOW}Setting up Python virtual environment...${NC}"
cd $PROJECT_ROOT
python3 -m venv venv

# 5. 仮想環境の有効化と依存関係のインストール
echo -e "${YELLOW}Installing dependencies...${NC}"
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 6. 環境設定ファイルのセットアップ
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Creating .env file...${NC}"
    cp config/.env.example .env
    echo -e "${RED}Please edit .env file with your configuration!${NC}"
fi

# 7. ログディレクトリの権限設定
echo -e "${YELLOW}Setting up log directory...${NC}"
mkdir -p logs
touch logs/.gitkeep

# 8. システムユーザーの作成（rootで実行時のみ）
if [ "$EUID" -eq 0 ]; then 
    if ! id "emailprocessor" &>/dev/null; then
        echo -e "${YELLOW}Creating system user...${NC}"
        useradd -r -s /bin/false emailprocessor
        chown -R emailprocessor:emailprocessor $PROJECT_ROOT
    fi
fi

# 9. データベース接続テスト
echo -e "${YELLOW}Testing database connection...${NC}"
python3 -c "
import sys
sys.path.insert(0, '.')
import asyncio
import asyncpg
from src.config import Config

async def test_db():
    try:
        conn = await asyncpg.connect(**Config.get_db_config())
        await conn.close()
        print('✓ Database connection successful')
        return True
    except Exception as e:
        print(f'✗ Database connection failed: {e}')
        return False

result = asyncio.run(test_db())
sys.exit(0 if result else 1)
" || {
    echo -e "${RED}Database connection failed. Please check your .env configuration.${NC}"
    exit 1
}

# 10. API接続テスト
echo -e "${YELLOW}Testing AI API connection...${NC}"
python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()

has_api = False
if os.getenv('OPENAI_API_KEY'):
    print('✓ OpenAI API key found')
    has_api = True
if os.getenv('DEEPSEEK_API_KEY'):
    print('✓ DeepSeek API key found')
    has_api = True
    
if not has_api:
    print('✗ No AI API keys found')
    exit(1)
" || {
    echo -e "${RED}No AI API keys found. Please add at least one API key to .env${NC}"
    exit 1
}

echo
echo -e "${GREEN}=== Setup completed successfully! ===${NC}"
echo
echo "Next steps:"
echo "1. Edit .env file with your configuration"
echo "2. Run test: python scripts/test_email_processor.py"
echo "3. Start service: python scripts/run_scheduler.py"
echo