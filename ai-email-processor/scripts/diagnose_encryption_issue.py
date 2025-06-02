# scripts/diagnose_encryption_issue.py
"""诊断数据库中的密码加密问题"""

import sys
import os
import asyncio

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncpg
from src.encryption_utils import decrypt, encrypt, DecryptionError
from src.config import Config


async def diagnose_password_issues():
    """诊断数据库中的密码加密问题"""
    print("🔍 诊断数据库密码加密问题")
    print("=" * 60)

    # 检查配置
    if not Config.ENCRYPTION_KEY:
        print("❌ 错误: 未找到 ENCRYPTION_KEY 环境变量")
        print("请检查 .env 文件中的 ENCRYPTION_KEY 设置")
        return

    print(f"✅ 当前加密密钥: {Config.ENCRYPTION_KEY[:10]}...")
    print()

    try:
        # 连接数据库
        conn = await asyncpg.connect(**Config.get_db_config())
        print("✅ 数据库连接成功")

        # 查询所有邮箱配置
        rows = await conn.fetch(
            """
            SELECT 
                s.id,
                s.tenant_id,
                t.name as tenant_name,
                s.smtp_host,
                s.smtp_port,
                s.smtp_username,
                s.smtp_password_encrypted,
                s.from_email,
                s.is_active,
                s.created_at
            FROM email_smtp_settings s
            LEFT JOIN tenants t ON s.tenant_id = t.id
            ORDER BY s.created_at DESC
        """
        )

        if not rows:
            print("⚠️  数据库中没有邮箱配置数据")
            print("\n📋 建议：")
            print("1. 运行 python scripts/interactive_password_tool.py 创建测试数据")
            print("2. 或者手动添加邮箱配置")
            return

        print(f"✅ 找到 {len(rows)} 个邮箱配置")
        print()

        # 分析每个配置
        for i, row in enumerate(rows, 1):
            print(f"📧 配置 {i}: {row['from_email']}")
            print("-" * 50)
            print(f"ID: {row['id']}")
            print(f"租户ID: {row['tenant_id']}")
            print(f"租户名称: {row['tenant_name'] or '未知'}")
            print(f"SMTP: {row['smtp_host']}:{row['smtp_port']}")
            print(f"用户名: {row['smtp_username']}")
            print(f"状态: {'活跃' if row['is_active'] else '非活跃'}")
            print(f"创建时间: {row['created_at']}")

            # 检查密码字段
            if row["smtp_password_encrypted"] is None:
                print("❌ 密码字段为空 (NULL)")
                print("   原因：没有存储任何密码数据")

            elif len(row["smtp_password_encrypted"]) == 0:
                print("❌ 密码字段为空字节")
                print("   原因：存储了空的字节数据")

            else:
                password_length = len(row["smtp_password_encrypted"])
                print(f"📊 密码数据长度: {password_length} 字节")
                print(
                    f"📊 密码数据预览: {row['smtp_password_encrypted'][:20].hex()}..."
                )

                # 尝试解密
                try:
                    decrypted = decrypt(
                        row["smtp_password_encrypted"], Config.ENCRYPTION_KEY
                    )
                    if decrypted:
                        print(f"✅ 解密成功！密码长度: {len(decrypted)} 字符")
                        print(
                            f"✅ 密码预览: {decrypted[:2]}{'*' * max(0, len(decrypted) - 4)}{decrypted[-2:] if len(decrypted) > 2 else ''}"
                        )
                    else:
                        print("⚠️  解密成功但密码为空")

                except DecryptionError as e:
                    print(f"❌ 解密失败: {e}")
                    print("   可能原因：")
                    print("   1. 密码使用了不同的加密密钥")
                    print("   2. 密码数据已损坏")
                    print("   3. 密码不是用Fernet算法加密的")

                    # 尝试判断是否是明文密码
                    try:
                        password_str = row["smtp_password_encrypted"].decode(
                            "utf-8", errors="ignore"
                        )
                        if password_str.isprintable() and len(password_str) > 0:
                            print(f"🤔 可能是明文密码: {password_str[:10]}...")
                        else:
                            print("🤔 不是可读的明文密码")
                    except:
                        print("🤔 无法作为文本解码")

                except Exception as e:
                    print(f"❌ 解密过程出错: {e}")

            print()

        await conn.close()

        # 提供解决建议
        print("=" * 60)
        print("💡 解决建议:")
        print("1. 如果密码解密失败，可能需要重新加密现有密码")
        print("2. 如果是明文密码，可以运行修复脚本转换为加密密码")
        print("3. 如果数据损坏，建议重新创建邮箱配置")
        print("4. 确保所有环境使用相同的 ENCRYPTION_KEY")

    except Exception as e:
        print(f"❌ 数据库操作失败: {e}")


async def fix_password_encryption():
    """修复密码加密问题"""
    print("\n" + "=" * 60)
    print("🔧 修复密码加密")
    print("=" * 60)

    try:
        conn = await asyncpg.connect(**Config.get_db_config())

        # 查找可能的明文密码
        rows = await conn.fetch(
            """
            SELECT id, smtp_username, smtp_password_encrypted, from_email
            FROM email_smtp_settings 
            WHERE smtp_password_encrypted IS NOT NULL
        """
        )

        fixed_count = 0

        for row in rows:
            try:
                # 先尝试解密
                decrypt(row["smtp_password_encrypted"], Config.ENCRYPTION_KEY)
                print(f"✅ {row['from_email']} - 密码已正确加密")
                continue

            except DecryptionError:
                # 解密失败，检查是否是明文
                try:
                    password_str = row["smtp_password_encrypted"].decode(
                        "utf-8", errors="strict"
                    )
                    if password_str.isprintable() and len(password_str.strip()) > 0:
                        print(f"🔄 修复 {row['from_email']} - 发现明文密码")

                        # 询问是否修复
                        user_input = (
                            input(f"是否将明文密码重新加密? (y/n): ").strip().lower()
                        )
                        if user_input == "y":
                            # 重新加密
                            encrypted = encrypt(password_str, Config.ENCRYPTION_KEY)

                            await conn.execute(
                                """
                                UPDATE email_smtp_settings 
                                SET smtp_password_encrypted = $1
                                WHERE id = $2
                            """,
                                encrypted,
                                row["id"],
                            )

                            print(f"✅ {row['from_email']} - 密码重新加密完成")
                            fixed_count += 1
                        else:
                            print(f"⏭️  跳过 {row['from_email']}")
                    else:
                        print(f"❓ {row['from_email']} - 无法识别的密码格式")

                except UnicodeDecodeError:
                    print(f"❓ {row['from_email']} - 非文本密码数据")

        await conn.close()

        print(f"\n🎯 修复完成！共修复了 {fixed_count} 个配置")

        if fixed_count > 0:
            print("\n📋 建议接下来：")
            print("1. 重新运行 python scripts/test_decryption.py 验证修复")
            print("2. 重新运行 python scripts/run_scheduler.py 测试邮件处理")

    except Exception as e:
        print(f"❌ 修复过程失败: {e}")


def main():
    print("🔍 邮箱密码加密诊断工具")
    print("分析数据库中的密码加密状态并提供修复建议\n")

    # 运行诊断
    asyncio.run(diagnose_password_issues())

    # 询问是否执行修复
    print("\n" + "=" * 60)
    fix_input = input("是否尝试自动修复密码加密问题? (y/n): ").strip().lower()
    if fix_input == "y":
        asyncio.run(fix_password_encryption())
    else:
        print("ℹ️  跳过自动修复")
        print("\n📋 手动修复步骤：")
        print("1. 如果需要重新创建配置：python scripts/interactive_password_tool.py")
        print("2. 如果需要更新现有配置：手动运行UPDATE SQL语句")


if __name__ == "__main__":
    main()
