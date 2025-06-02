# scripts/generate_test_passwords.py
"""生成测试用的加密密码数据"""

import sys
import os
import uuid
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.encryption_utils import encrypt
from src.config import Config


def generate_encrypted_password(plain_password: str) -> bytes:
    """生成加密后的密码"""
    try:
        encrypted = encrypt(plain_password, Config.ENCRYPTION_KEY)
        return encrypted
    except Exception as e:
        print(f"加密失败: {e}")
        return None


def main():
    print("=== 测试密码加密工具 ===")
    print(
        f"使用加密密钥: {Config.ENCRYPTION_KEY[:10]}..."
        if Config.ENCRYPTION_KEY
        else "未设置加密密钥"
    )
    print()

    if not Config.ENCRYPTION_KEY:
        print("❌ 错误: 未找到 ENCRYPTION_KEY 环境变量")
        print("请在 .env 文件中设置 ENCRYPTION_KEY")
        return

    # 测试用的邮箱配置数据
    test_configs = [
        {
            "name": "onamae测试配置",
            "smtp_host": "mail92.onamae.ne.jp",
            "smtp_port": 465,
            "smtp_username": "ryushigen@toyousoft.co.jp",
            "plain_password": "1994Lzy.",  # 请替换为实际的应用密码
            "security_protocol": "SSL",
            "from_email": "ryushigen@toyousoft.co.jp",
            "from_name": "测试发件人",
        },
        # {
        #     "name": "Outlook测试配置",
        #     "smtp_host": "smtp.outlook.com",
        #     "smtp_port": 587,
        #     "smtp_username": "test@outlook.com",
        #     "plain_password": "your_outlook_password",  # 请替换为实际密码
        #     "security_protocol": "TLS",
        #     "from_email": "test@outlook.com",
        #     "from_name": "Outlook发件人",
        # },
        # {
        #     "name": "QQ邮箱测试配置",
        #     "smtp_host": "smtp.qq.com",
        #     "smtp_port": 587,
        #     "smtp_username": "test@qq.com",
        #     "plain_password": "your_qq_auth_code",  # 请替换为QQ邮箱授权码
        #     "security_protocol": "TLS",
        #     "from_email": "test@qq.com",
        #     "from_name": "QQ发件人",
        # },
    ]

    print("生成的加密密码和SQL插入语句:")
    print("=" * 80)

    for i, config in enumerate(test_configs, 1):
        print(f"\n{i}. {config['name']}")
        print("-" * 40)

        # 生成加密密码
        encrypted_password = generate_encrypted_password(config["plain_password"])

        if encrypted_password:
            config_id = str(uuid.uuid4())
            tenant_id = "33723dd6-cf28-4dab-975c-f883f5389d04"  # 测试租户ID

            print(f"原始密码: {config['plain_password']}")
            print(f"加密后 (Python bytes): {encrypted_password}")
            print(f"加密后 (十六进制): {encrypted_password.hex()}")
            print()

            # 生成SQL插入语句
            sql = f"""
-- {config['name']}
INSERT INTO email_smtp_settings (
    id, 
    tenant_id, 
    smtp_host, 
    smtp_port, 
    smtp_username, 
    smtp_password_encrypted, 
    security_protocol, 
    from_email, 
    from_name, 
    is_default, 
    is_active, 
    created_at
) VALUES (
    '{config_id}',
    '{tenant_id}',
    '{config['smtp_host']}',
    {config['smtp_port']},
    '{config['smtp_username']}',
    '\\x{encrypted_password.hex()}',  -- PostgreSQL bytea 格式
    '{config['security_protocol']}',
    '{config['from_email']}',
    '{config['from_name']}',
    {str(i == 1).lower()},  -- 第一个设为默认
    true,
    '{datetime.now().isoformat()}'
);"""
            print(sql)

    print("\n" + "=" * 80)
    print("📋 使用说明:")
    print("1. 请先修改上面配置中的密码为真实的邮箱密码")
    print("2. 重新运行此脚本生成新的加密数据")
    print("3. 将生成的SQL语句复制到数据库中执行")
    print("4. 确保租户表中存在对应的 tenant_id")
    print()
    print("⚠️  重要提醒:")
    print("- Gmail需要使用应用专用密码，不是账户密码")
    print("- QQ邮箱需要使用授权码，不是QQ密码")
    print("- 请确保 .env 文件中的 ENCRYPTION_KEY 与生产环境一致")


if __name__ == "__main__":
    main()
