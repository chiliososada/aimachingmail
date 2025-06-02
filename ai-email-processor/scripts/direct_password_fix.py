# scripts/direct_password_fix.py
"""直接使用SQL的密码修复脚本"""

import sys
import os
import asyncio
import getpass

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncpg
from src.encryption_utils import encrypt, decrypt, DecryptionError
from src.config import Config


def get_db_config():
    """获取数据库连接配置"""
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "database": os.getenv("DB_NAME", "ai_matching"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", ""),
    }


async def direct_password_update():
    """使用十六进制字符串直接更新密码"""
    print("🔧 直接密码更新")
    print("-" * 30)

    try:
        conn = await asyncpg.connect(**get_db_config())

        # 查找问题配置
        problem_config = await conn.fetchrow(
            """
            SELECT id, tenant_id, smtp_username, from_email, smtp_password_encrypted
            FROM email_smtp_settings 
            WHERE tenant_id = '33723dd6-cf28-4dab-975c-f883f5389d04'
            AND id = 'c8f04684-79d1-41fa-be30-b9c7652568cb'
        """
        )

        if not problem_config:
            print("❌ 未找到指定的配置")
            await conn.close()
            return False

        print(f"📧 找到配置: {problem_config['from_email']}")
        print(f"   ID: {problem_config['id']}")

        # 输入新密码
        print(f"\n🔐 请输入 {problem_config['from_email']} 的正确密码:")
        password = getpass.getpass("密码: ")

        if not password.strip():
            print("❌ 密码不能为空")
            await conn.close()
            return False

        # 加密新密码
        encrypted_password = encrypt(password, Config.ENCRYPTION_KEY)
        print(f"✅ 密码加密成功，长度: {len(encrypted_password)} 字节")

        # 转换为十六进制字符串
        hex_password = encrypted_password.hex()
        print(f"📊 十六进制长度: {len(hex_password)} 字符")
        print(f"📊 十六进制预览: {hex_password[:40]}...")

        # 使用十六进制字符串更新（PostgreSQL的\\x语法）
        result = await conn.execute(
            f"""
            UPDATE email_smtp_settings 
            SET smtp_password_encrypted = '\\x{hex_password}'
            WHERE id = $1
        """,
            problem_config["id"],
        )

        print(f"✅ 密码更新成功: {result}")

        # 验证更新
        print("\n🔍 验证更新结果...")
        updated_config = await conn.fetchrow(
            """
            SELECT smtp_password_encrypted 
            FROM email_smtp_settings 
            WHERE id = $1
        """,
            problem_config["id"],
        )

        if updated_config:
            try:
                decrypted = decrypt(
                    updated_config["smtp_password_encrypted"], Config.ENCRYPTION_KEY
                )
                if decrypted and len(decrypted.strip()) > 0:
                    print("✅ 验证成功！密码可以正确解密")
                    print(f"   密码长度: {len(decrypted)} 字符")
                    print(
                        f"   密码预览: {decrypted[:2]}{'*' * max(0, len(decrypted) - 4)}{decrypted[-2:] if len(decrypted) > 2 else ''}"
                    )
                    await conn.close()
                    return True
                else:
                    print("❌ 验证失败：解密后密码为空")
            except DecryptionError as e:
                print(f"❌ 验证失败：{e}")

        await conn.close()
        return False

    except Exception as e:
        print(f"❌ 密码更新失败: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_email_processor_integration():
    """测试EmailProcessor集成"""
    print("\n🧪 测试 EmailProcessor 集成")
    print("-" * 40)

    try:
        from src.email_processor import EmailProcessor

        # 创建EmailProcessor实例
        processor = EmailProcessor(
            db_config=Config.get_db_config(), ai_config=Config.get_ai_config()
        )

        await processor.initialize()
        print("✅ EmailProcessor初始化成功")

        # 测试获取SMTP设置
        tenant_id = "33723dd6-cf28-4dab-975c-f883f5389d04"
        settings_list = await processor.get_smtp_settings(tenant_id)

        if not settings_list:
            print("❌ 没有找到SMTP设置")
            await processor.close()
            return False

        print(f"✅ 成功获取 {len(settings_list)} 个SMTP配置")

        for i, settings in enumerate(settings_list, 1):
            print(f"\n📨 SMTP配置 {i}:")
            print(f"  ID: {settings.id}")
            print(f"  主机: {settings.smtp_host}:{settings.smtp_port}")
            print(f"  用户名: {settings.smtp_username}")
            print(
                f"  密码状态: {'已解密 ✅' if settings.smtp_password else '解密失败 ❌'}"
            )
            print(f"  发件人: {settings.from_name} <{settings.from_email}>")
            print(f"  协议: {settings.security_protocol}")

            if settings.smtp_password:
                print(f"  密码长度: {len(settings.smtp_password)} 字符")
                # 不显示密码内容，只显示长度确认
                print(f"  密码确认: 非空字符串 ✅")

        await processor.close()
        print("\n✅ EmailProcessor测试完成")
        return True

    except Exception as e:
        print(f"❌ EmailProcessor测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_scheduler():
    """测试调度器能否正常运行"""
    print("\n🚀 测试调度器")
    print("-" * 20)

    try:
        # 导入调度器的主要逻辑
        from src.email_processor import main as email_main

        print("🔄 运行一次邮件处理...")
        await email_main()
        print("✅ 邮件处理完成")
        return True

    except Exception as e:
        print(f"❌ 邮件处理测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    print("🔧 直接密码修复工具")
    print("解决 ryushigen@toyousoft.co.jp 的 BYTEA 字段问题")
    print("=" * 60)

    # 检查加密密钥
    if not Config.ENCRYPTION_KEY:
        print("❌ 错误: 未找到 ENCRYPTION_KEY 环境变量")
        return

    print(f"✅ 加密密钥: {Config.ENCRYPTION_KEY[:10]}...")

    # 1. 直接更新密码
    print("\n第一步：直接更新密码字段")
    if not await direct_password_update():
        print("❌ 密码更新失败，无法继续")
        return

    # 2. 测试EmailProcessor集成
    print("\n第二步：测试EmailProcessor集成")
    if not await test_email_processor_integration():
        print("❌ EmailProcessor集成测试失败")
        return

    # 3. 测试调度器
    print("\n第三步：测试调度器")
    if await test_scheduler():
        print("✅ 调度器测试成功")
    else:
        print("⚠️  调度器测试失败，但密码修复成功")

    print("\n" + "=" * 60)
    print("🎉 密码修复完成！")
    print("\n📋 现在可以运行:")
    print("1. 邮件处理测试: python scripts/test_email_processor.py")
    print("2. 启动调度器: python scripts/run_scheduler.py")

    print("\n🔍 期望的调度器输出:")
    print("  ✅ DeepSeek client initialized...")
    print("  ✅ Database pool created successfully")
    print("  ✅ Processing emails for tenant: 33723dd6...")
    print("  ✅ Fetched 0 new emails for tenant...")
    print("  (不再有密码解密错误)")


if __name__ == "__main__":
    asyncio.run(main())
