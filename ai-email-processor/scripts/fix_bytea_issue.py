# scripts/fix_bytea_issue.py
"""修复PostgreSQL BYTEA字段问题"""

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


def hex_string_to_bytes(hex_str):
    """将十六进制字符串转换为字节"""
    # 移除可能的 \x 前缀
    if hex_str.startswith("\\x"):
        hex_str = hex_str[2:]

    try:
        return bytes.fromhex(hex_str)
    except ValueError as e:
        print(f"❌ 十六进制转换失败: {e}")
        return None


async def fix_password_with_conversion():
    """修复密码，正确处理字符串到字节的转换"""
    print("🔧 修复BYTEA字段问题")
    print("-" * 30)

    try:
        conn = await asyncpg.connect(**get_db_config())

        # 查找配置
        config = await conn.fetchrow(
            """
            SELECT id, from_email, smtp_password_encrypted
            FROM email_smtp_settings 
            WHERE id = 'c8f04684-79d1-41fa-be30-b9c7652568cb'
        """
        )

        if not config:
            print("❌ 未找到配置")
            await conn.close()
            return False

        print(f"📧 配置: {config['from_email']}")

        # 当前密码数据分析
        current_password_data = config["smtp_password_encrypted"]
        print(f"当前密码数据类型: {type(current_password_data)}")
        print(f"当前密码数据长度: {len(current_password_data)}")
        print(f"当前密码数据预览: {current_password_data[:40]}...")

        # 尝试转换当前数据
        if isinstance(current_password_data, str):
            print("\n🔄 尝试转换现有的字符串数据...")

            # 移除可能的前缀并转换
            clean_hex = current_password_data
            if clean_hex.startswith("\\x"):
                clean_hex = clean_hex[2:]

            try:
                converted_bytes = bytes.fromhex(clean_hex)
                print(f"✅ 转换成功，长度: {len(converted_bytes)} 字节")

                # 尝试解密转换后的数据
                try:
                    decrypted = decrypt(converted_bytes, Config.ENCRYPTION_KEY)
                    print(f"✅ 现有数据解密成功！")
                    print(f"   密码长度: {len(decrypted)} 字符")
                    print(
                        f"   密码预览: {decrypted[:2]}{'*' * max(0, len(decrypted) - 4)}{decrypted[-2:] if len(decrypted) > 2 else ''}"
                    )

                    await conn.close()

                    print("\n🎉 发现：现有密码数据实际上是可用的！")
                    print("问题在于EmailProcessor的解密逻辑需要修复。")
                    return True

                except DecryptionError as e:
                    print(f"❌ 现有数据解密失败: {e}")

            except ValueError as e:
                print(f"❌ 十六进制转换失败: {e}")

        # 如果现有数据不可用，创建新密码
        print("\n🔐 创建新的正确格式密码...")

        # 输入新密码
        print(f"请输入 {config['from_email']} 的密码:")
        password = getpass.getpass("密码: ")

        if not password.strip():
            print("❌ 密码不能为空")
            await conn.close()
            return False

        # 加密新密码
        encrypted_data = encrypt(password, Config.ENCRYPTION_KEY)
        print(f"✅ 新密码加密成功，长度: {len(encrypted_data)} 字节")

        # 直接以二进制格式存储（不转换为十六进制）
        await conn.execute(
            """
            UPDATE email_smtp_settings 
            SET smtp_password_encrypted = $1
            WHERE id = $2
        """,
            encrypted_data,
            config["id"],
        )

        print("✅ 密码更新完成")

        # 验证新存储的数据
        updated_config = await conn.fetchrow(
            """
            SELECT smtp_password_encrypted
            FROM email_smtp_settings 
            WHERE id = $1
        """,
            config["id"],
        )

        if updated_config:
            new_password_data = updated_config["smtp_password_encrypted"]
            print(f"\n🔍 验证新存储的数据:")
            print(f"   数据类型: {type(new_password_data)}")
            print(f"   数据长度: {len(new_password_data)}")

            if isinstance(new_password_data, bytes):
                # 正确的字节类型
                try:
                    decrypted = decrypt(new_password_data, Config.ENCRYPTION_KEY)
                    print(f"✅ 新密码解密成功！")
                    print(f"   密码匹配: {'✅' if decrypted == password else '❌'}")
                    await conn.close()
                    return True
                except DecryptionError as e:
                    print(f"❌ 新密码解密失败: {e}")

            elif isinstance(new_password_data, str):
                # 仍然是字符串，需要转换
                print("⚠️  仍然存储为字符串，尝试转换...")
                try:
                    converted = hex_string_to_bytes(new_password_data)
                    if converted:
                        decrypted = decrypt(converted, Config.ENCRYPTION_KEY)
                        print(f"✅ 转换后解密成功！")
                        print(f"   密码匹配: {'✅' if decrypted == password else '❌'}")
                        await conn.close()
                        return True
                except Exception as e:
                    print(f"❌ 转换解密失败: {e}")

        await conn.close()
        return False

    except Exception as e:
        print(f"❌ 修复失败: {e}")
        import traceback

        traceback.print_exc()
        return False


async def update_email_processor():
    """更新EmailProcessor以正确处理字符串类型的BYTEA字段"""
    print("\n🔧 需要更新EmailProcessor的解密逻辑")
    print("-" * 40)

    print("检测到PostgreSQL BYTEA字段返回字符串而不是字节。")
    print("需要在EmailProcessor中添加转换逻辑。")

    print("\n📝 需要修改的文件: src/email_processor.py")
    print("在 get_smtp_settings 方法中添加:")
    print(
        """
    # 修复BYTEA字段类型转换
    if isinstance(row["smtp_password_encrypted"], str):
        # 如果是字符串，转换为字节
        hex_str = row["smtp_password_encrypted"]
        if hex_str.startswith('\\\\x'):
            hex_str = hex_str[2:]
        try:
            password_bytes = bytes.fromhex(hex_str)
            decrypted_password = decrypt(password_bytes, Config.ENCRYPTION_KEY)
        except ValueError:
            logger.error(f"Failed to convert hex string to bytes for SMTP setting {row['id']}")
            continue
    else:
        # 正常的字节类型处理
        decrypted_password = decrypt(row["smtp_password_encrypted"], Config.ENCRYPTION_KEY)
    """
    )


async def test_current_state():
    """测试当前状态，确认修复是否有效"""
    print("\n🧪 测试当前EmailProcessor")
    print("-" * 30)

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
            print(f"  主机: {settings.smtp_host}:{settings.smtp_port}")
            print(f"  用户名: {settings.smtp_username}")
            print(
                f"  密码状态: {'已解密 ✅' if settings.smtp_password else '解密失败 ❌'}"
            )
            print(f"  发件人: {settings.from_name} <{settings.from_email}>")

            if settings.smtp_password:
                print(f"  密码长度: {len(settings.smtp_password)} 字符")
                print("  🎉 EmailProcessor现在可以正确解密密码了！")

        await processor.close()
        return True

    except Exception as e:
        print(f"❌ EmailProcessor测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    print("🔧 BYTEA字段问题修复工具")
    print("解决PostgreSQL字符串/字节转换问题")
    print("=" * 60)

    # 检查配置
    if not Config.ENCRYPTION_KEY:
        print("❌ 错误: 未找到 ENCRYPTION_KEY 环境变量")
        return

    print(f"✅ 加密密钥: {Config.ENCRYPTION_KEY[:10]}...")

    # 1. 修复密码数据
    print("\n第一步：修复密码数据")
    if await fix_password_with_conversion():
        print("✅ 密码数据修复成功")
    else:
        print("❌ 密码数据修复失败")
        return

    # 2. 更新EmailProcessor指导
    await update_email_processor()

    # 3. 测试当前状态
    print("\n第三步：测试EmailProcessor")
    if await test_current_state():
        print("\n🎉 完全修复成功！")
        print("\n📋 现在可以运行:")
        print("  python scripts/test_email_processor.py")
        print("  python scripts/run_scheduler.py")
    else:
        print("\n⚠️  需要手动修改EmailProcessor代码")
        print("请按照上面的指导修改 src/email_processor.py")


if __name__ == "__main__":
    asyncio.run(main())
