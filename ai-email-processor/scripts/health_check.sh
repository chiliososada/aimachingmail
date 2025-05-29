# scripts/health_check.sh
#!/bin/bash

SERVICE="email-processor"
LOG_FILE="/opt/ai-email-processor/logs/health_check.log"

# サービスが動いているか確認
if ! systemctl is-active --quiet $SERVICE; then
    echo "$(date): $SERVICE is down. Attempting restart..." >> $LOG_FILE
    systemctl restart $SERVICE
    
    # 再起動後の確認
    sleep 5
    if systemctl is-active --quiet $SERVICE; then
        echo "$(date): $SERVICE restarted successfully" >> $LOG_FILE
    else
        echo "$(date): Failed to restart $SERVICE" >> $LOG_FILE
        # アラート送信（メール、Slackなど）
    fi
fi

# 処理状況の確認
PYTHON="/opt/ai-email-processor/venv/bin/python"
$PYTHON -c "
import sys
sys.path.insert(0, '/opt/ai-email-processor')
import asyncio
import asyncpg
from src.config import Config
from datetime import datetime, timedelta

async def check_health():
    try:
        conn = await asyncpg.connect(**Config.get_db_config())
        
        # 過去1時間の処理状況を確認
        result = await conn.fetchrow('''
            SELECT COUNT(*) as total,
                   COUNT(CASE WHEN processing_status = 'error' THEN 1 END) as errors
            FROM receive_emails
            WHERE created_at >= NOW() - INTERVAL '1 hour'
        ''')
        
        if result['total'] > 0 and result['errors'] / result['total'] > 0.5:
            print(f'WARNING: High error rate detected: {result[\"errors\"]} / {result[\"total\"]}')
            
        await conn.close()
        return True
    except Exception as e:
        print(f'Database check failed: {e}')
        return False

asyncio.run(check_health())
"