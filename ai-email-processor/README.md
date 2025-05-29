# AI メール処理システム

## 概要

このシステムは、受信メールを自動的に分析し、案件情報や技術者情報を抽出してデータベースに構造化して保存するPythonベースのバックエンドシステムです。

## 主な機能

1. **メール自動取得**: 設定されたメールアカウントから新着メールを定期的に取得
2. **AI分類**: メールを以下のカテゴリーに自動分類
   - 案件関連（project_related）
   - 技術者関連（engineer_related）
   - その他（other）
   - 未分類（unclassified）
3. **情報抽出**: AIを使用してメールから構造化データを抽出
4. **データベース保存**: 抽出した情報を適切なテーブルに保存

## システムアーキテクチャ

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  メールサーバー   │────▶│  Email Processor │────▶│   PostgreSQL    │
│   (IMAP/POP3)   │     │   (Python)       │     │   Database      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │   AI Provider   │
                        │ (OpenAI/DeepSeek)│
                        └─────────────────┘
```

## インストール

### 1. 前提条件

- Python 3.11以上
- PostgreSQL 15以上
- OpenAI APIキー または DeepSeek APIキー

### 2. 依存関係のインストール

```bash
# リポジトリのクローン
git clone <repository-url>
cd email-processor

# 仮想環境の作成
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 依存関係のインストール
pip install -r requirements.txt
```

### 3. 環境設定

```bash
# .env.exampleをコピーして編集
cp .env.example .env

# 必要な設定を記入
# - データベース接続情報
# - AI APIキー
# - 暗号化キー
```

### 4. データベースのセットアップ

```bash
# SQLスクリプトを実行
psql -U postgres -d ai_matching < new.sql
psql -U postgres -d ai_matching < newadd.sql
```

## 使用方法

### 1. スケジューラーの起動

```bash
# 通常起動
python run_scheduler.py

# バックグラウンドで起動
nohup python run_scheduler.py > /dev/null 2>&1 &
```

### 2. 単発実行

```python
import asyncio
from email_processor import main

# メール処理を1回実行
asyncio.run(main())
```

### 3. テストの実行

```bash
# テストスクリプトの実行
python test_email_processor.py
```

## 設定項目

### メール設定（email_smtp_settings テーブル）

画面から以下の項目を設定：

- **SMTPホスト**: メールサーバーのホスト名
- **SMTPポート**: ポート番号（通常587または465）
- **ユーザー名**: メールアカウントのユーザー名
- **パスワード**: メールアカウントのパスワード（暗号化して保存）
- **セキュリティプロトコル**: TLS/SSL/None

### AI設定

`.env`ファイルで設定：

```env
# OpenAI使用時
DEFAULT_AI_PROVIDER=openai
OPENAI_API_KEY=your_key_here
OPENAI_MODEL_CLASSIFY=gpt-3.5-turbo
OPENAI_MODEL_EXTRACT=gpt-4

# DeepSeek使用時
DEFAULT_AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_key_here
```

## データフロー

1. **メール取得**
   - `email_smtp_settings`から設定を読み込み
   - IMAPでメールサーバーに接続
   - 未読メールを取得

2. **AI分析**
   - メールの内容をAIで分類
   - 案件または技術者情報を抽出

3. **データ保存**
   - `receive_emails`テーブルに元メールを保存
   - 案件の場合：`projects`テーブルに保存
   - 技術者の場合：`engineers`テーブルに保存

## Dockerでの運用

### 1. イメージのビルド

```bash
docker build -t email-processor .
```

### 2. Docker Composeで起動

```bash
docker-compose up -d
```

### 3. ログの確認

```bash
docker logs -f ai-email-processor
```

## systemdサービスとして登録

```bash
# サービスファイルをコピー
sudo cp email-processor.service /etc/systemd/system/

# サービスの有効化と起動
sudo systemctl enable email-processor
sudo systemctl start email-processor

# ステータス確認
sudo systemctl status email-processor
```

## トラブルシューティング

### メールが取得できない場合

1. SMTP/IMAP設定を確認
2. ファイアウォール設定を確認
3. 2段階認証の場合はアプリパスワードを使用

### AI処理エラー

1. APIキーが正しいか確認
2. API利用制限に達していないか確認
3. ネットワーク接続を確認

### データベースエラー

1. PostgreSQLが起動しているか確認
2. 接続情報が正しいか確認
3. テーブルが作成されているか確認

## 監視とメンテナンス

### ログファイル

- アプリケーションログ: `email_processor.log`
- エラーログ: ログレベルERROR以上を監視

### 定期メンテナンス

1. **ログローテーション**: 週次でログファイルをローテーション
2. **データベース最適化**: 月次でVACUUMを実行
3. **古いメールの削除**: 3ヶ月以上前の処理済みメールを削除

## セキュリティ考慮事項

1. **APIキーの管理**: 環境変数で管理し、コードにハードコードしない
2. **パスワード暗号化**: メールパスワードは暗号化して保存
3. **アクセス制限**: データベースへのアクセスを制限
4. **ログの管理**: 機密情報をログに出力しない

## パフォーマンスチューニング

1. **バッチサイズ**: `EMAIL_BATCH_SIZE`で調整（デフォルト: 50）
2. **処理間隔**: `EMAIL_CHECK_INTERVAL`で調整（デフォルト: 10分）
3. **データベースプール**: `DB_POOL_MIN/MAX`で調整

## 今後の拡張予定

1. **添付ファイル処理**: PDF履歴書の自動解析
2. **マルチテナント対応の強化**: 並列処理の実装
3. **Web管理画面**: 処理状況の可視化
4. **通知機能**: 重要なメールの即時通知

## ライセンス

[ライセンス情報を記載]

## サポート

問題が発生した場合は、以下の情報と共に報告してください：

- エラーログ
- 実行環境（OS、Pythonバージョン）
- 再現手順