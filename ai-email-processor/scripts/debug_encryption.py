# scripts/debug_encryption.py
"""调试加密解密问题的详细脚本"""

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


async def debug_encryption_cycle():
    """调试完整的加密解密周期"""
    print("🔍 调试加密解密周期")
    print("=" * 50)

    # 输入测试密码
    print("请输入测试密码:")
    test_password = getpass.getpass("测试密码: ")

    if not test_password.strip():
        print("❌ 密码不能为空")
        return False

    print(f"\n📝 原始密码信息:")
    print(f"   长度: {len(test_password)} 字符")
    print(f"   类型: {type(test_password)}")
    print(f"   编码测试: {test_password.encode('utf-8')[:20]}...")

    # 步骤1：加密测试
    print(f"\n🔐 步骤1：加密测试")
    try:
        encrypted_data = encrypt(test_password, Config.ENCRYPTION_KEY)
        print(f"✅ 加密成功")
        print(f"   加密数据长度: {len(encrypted_data)} 字节")
        print(f"   加密数据类型: {type(encrypted_data)}")
        print(f"   加密数据预览: {encrypted_data[:20]}...")
        print(f"   十六进制: {encrypted_data.hex()[:40]}...")
    except Exception as e:
        print(f"❌ 加密失败: {e}")
        return False

    # 步骤2：直接解密测试（不通过数据库）
    print(f"\n🔓 步骤2：直接解密测试")
    try:
        decrypted_direct = decrypt(encrypted_data, Config.ENCRYPTION_KEY)
        print(f"✅ 直接解密成功")
        print(f"   解密结果长度: {len(decrypted_direct)} 字符")
        print(f"   解密结果类型: {type(decrypted_direct)}")
        print(f"   密码匹配: {'✅' if decrypted_direct == test_password else '❌'}")
        if decrypted_direct != test_password:
            print(f"   原始: '{test_password}'")
            print(f"   解密: '{decrypted_direct}'")
    except Exception as e:
        print(f"❌ 直接解密失败: {e}")
        return False

    # 步骤3：数据库存储测试
    print(f"\n💾 步骤3：数据库存储测试")
    try:
        conn = await asyncpg.connect(**get_db_config())

        # 方法1：使用参数绑定（可能失败）
        print("   尝试方法1：参数绑定...")
        try:
            result1 = await conn.execute(
                """
                UPDATE email_smtp_settings 
                SET smtp_password_encrypted = $1::bytea
                WHERE id = 'c8f04684-79d1-41fa-be30-b9c7652568cb'
            """,
                encrypted_data,
            )
            print(f"   ✅ 方法1成功: {result1}")

            # 读取验证
            stored_data1 = await conn.fetchval(
                """
                SELECT smtp_password_encrypted 
                FROM email_smtp_settings 
                WHERE id = 'c8f04684-79d1-41fa-be30-b9c7652568cb'
            """
            )

            print(f"   读取数据长度: {len(stored_data1)} 字节")
            print(f"   读取数据类型: {type(stored_data1)}")
            print(f"   数据匹配: {'✅' if stored_data1 == encrypted_data else '❌'}")

            # 解密验证
            try:
                decrypted1 = decrypt(stored_data1, Config.ENCRYPTION_KEY)
                print(
                    f"   ✅ 方法1解密成功: 密码匹配 {'✅' if decrypted1 == test_password else '❌'}"
                )
            except Exception as e:
                print(f"   ❌ 方法1解密失败: {e}")

        except Exception as e:
            print(f"   ❌ 方法1失败: {e}")

        print()

        # 方法2：使用十六进制字符串
        print("   尝试方法2：十六进制字符串...")
        try:
            hex_data = encrypted_data.hex()
            result2 = await conn.execute(
                f"""
                UPDATE email_smtp_settings 
                SET smtp_password_encrypted = '\\x{hex_data}'
                WHERE id = 'c8f04684-79d1-41fa-be30-b9c7652568cb'
            """
            )
            print(f"   ✅ 方法2成功: {result2}")

            # 读取验证
            stored_data2 = await conn.fetchval(
                """
                SELECT smtp_password_encrypted 
                FROM email_smtp_settings 
                WHERE id = 'c8f04684-79d1-41fa-be30-b9c7652568cb'
            """
            )

            print(f"   读取数据长度: {len(stored_data2)} 字节")
            print(f"   读取数据类型: {type(stored_data2)}")
            print(f"   数据匹配: {'✅' if stored_data2 == encrypted_data else '❌'}")

            # 详细比较
            if stored_data2 != encrypted_data:
                print(f"   原始数据: {encrypted_data.hex()[:40]}...")
                print(f"   存储数据: {stored_data2.hex()[:40]}...")

            # 解密验证
            try:
                decrypted2 = decrypt(stored_data2, Config.ENCRYPTION_KEY)
                print(
                    f"   ✅ 方法2解密成功: 密码匹配 {'✅' if decrypted2 == test_password else '❌'}"
                )
                if decrypted2 == test_password:
                    print(f"   🎉 找到有效的存储方法！")
                    await conn.close()
                    return True
            except Exception as e:
                print(f"   ❌ 方法2解密失败: {e}")

        except Exception as e:
            print(f"   ❌ 方法2失败: {e}")

        await conn.close()

    except Exception as e:
        print(f"❌ 数据库操作失败: {e}")
        return False

    return False


async def check_current_database_state():
    """检查当前数据库中的密码状态"""
    print("\n🔍 检查当前数据库状态")
    print("-" * 30)

    try:
        conn = await asyncpg.connect(**get_db_config())

        config = await conn.fetchrow(
            """
            SELECT id, smtp_username, from_email, smtp_password_encrypted
            FROM email_smtp_settings 
            WHERE id = 'c8f04684-79d1-41fa-be30-b9c7652568cb'
        """
        )

        if not config:
            print("❌ 未找到指定配置")
            await conn.close()
            return

        print(f"📧 配置: {config['from_email']}")
        print(f"   ID: {config['id']}")

        if config["smtp_password_encrypted"]:
            password_data = config["smtp_password_encrypted"]
            print(f"   密码数据长度: {len(password_data)} 字节")
            print(f"   密码数据类型: {type(password_data)}")
            print(f"   十六进制预览: {password_data.hex()[:40]}...")

            # 尝试解密
            try:
                decrypted = decrypt(password_data, Config.ENCRYPTION_KEY)
                print(f"   ✅ 当前密码可以解密")
                print(f"   解密长度: {len(decrypted)} 字符")
            except Exception as e:
                print(f"   ❌ 当前密码解密失败: {e}")
        else:
            print("   ❌ 密码数据为空")

        await conn.close()

    except Exception as e:
        print(f"❌ 检查失败: {e}")


async def test_encryption_key():
    """测试加密密钥是否正确"""
    print("\n🔑 测试加密密钥")
    print("-" * 20)

    print(f"当前加密密钥: {Config.ENCRYPTION_KEY[:10]}...")
    print(f"密钥长度: {len(Config.ENCRYPTION_KEY)} 字符")

    # 简单的加密解密测试
    test_text = "hello_world_123"
    try:
        encrypted = encrypt(test_text, Config.ENCRYPTION_KEY)
        decrypted = decrypt(encrypted, Config.ENCRYPTION_KEY)

        print(f"✅ 加密密钥测试: {'通过' if decrypted == test_text else '失败'}")

        if decrypted != test_text:
            print(f"   原始: '{test_text}'")
            print(f"   解密: '{decrypted}'")

    except Exception as e:
        print(f"❌ 加密密钥测试失败: {e}")


async def main():
    print("🐛 加密解密问题调试工具")
    print("深入分析密码存储和解密问题")
    print("=" * 60)

    # 检查配置
    if not Config.ENCRYPTION_KEY:
        print("❌ 错误: 未找到 ENCRYPTION_KEY 环境变量")
        return

    # 测试1：检查加密密钥
    await test_encryption_key()

    # 测试2：检查当前数据库状态
    await check_current_database_state()

    # 测试3：完整调试周期
    print("\n" + "=" * 60)
    print("开始完整的加密调试测试")
    if await debug_encryption_cycle():
        print("\n🎉 找到有效的解决方案！")

        # 最终验证
        print("\n🔄 最终验证...")
        await check_current_database_state()

        print("\n📋 现在可以测试:")
        print("  python scripts/test_email_processor.py")
        print("  python scripts/run_scheduler.py")
    else:
        print("\n❌ 未找到有效解决方案")
        print("\n🤔 可能的问题:")
        print("1. 加密密钥不匹配")
        print("2. 数据库字段类型问题")
        print("3. PostgreSQL版本兼容性问题")
        print("4. 原始密码可能已经不正确")


if __name__ == "__main__":
    asyncio.run(main())
