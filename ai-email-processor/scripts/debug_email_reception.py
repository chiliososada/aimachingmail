# scripts/debug_email_reception.py
"""调试邮件接收问题"""

import sys
import os
import asyncio
import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncpg
from src.email_processor import EmailProcessor
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


async def check_processed_emails():
    """检查数据库中已处理的邮件"""
    print("🗄️  检查数据库中的邮件记录")
    print("-" * 40)

    try:
        conn = await asyncpg.connect(**get_db_config())

        # 查询最近的邮件记录
        recent_emails = await conn.fetch(
            """
            SELECT 
                id,
                subject,
                sender_email,
                email_type,
                processing_status,
                received_at,
                created_at
            FROM receive_emails 
            WHERE tenant_id = '33723dd6-cf28-4dab-975c-f883f5389d04'
            ORDER BY created_at DESC 
            LIMIT 10
        """
        )

        if not recent_emails:
            print("📭 数据库中没有邮件记录")
        else:
            print(f"📨 找到 {len(recent_emails)} 条最近的邮件记录:")
            for i, email_record in enumerate(recent_emails, 1):
                print(f"\n{i}. {email_record['subject'][:50]}...")
                print(f"   发件人: {email_record['sender_email']}")
                print(f"   类型: {email_record['email_type']}")
                print(f"   状态: {email_record['processing_status']}")
                print(f"   接收时间: {email_record['received_at']}")
                print(f"   处理时间: {email_record['created_at']}")

        await conn.close()

    except Exception as e:
        print(f"❌ 检查数据库失败: {e}")


async def test_direct_imap_connection():
    """直接测试IMAP连接和邮件获取"""
    print("\n📧 直接测试IMAP连接")
    print("-" * 30)

    try:
        # 获取SMTP设置
        processor = EmailProcessor(
            db_config=Config.get_db_config(), ai_config=Config.get_ai_config()
        )
        await processor.initialize()

        tenant_id = "33723dd6-cf28-4dab-975c-f883f5389d04"
        settings_list = await processor.get_smtp_settings(tenant_id)

        if not settings_list:
            print("❌ 没有找到SMTP设置")
            await processor.close()
            return

        settings = settings_list[0]  # 使用第一个配置
        print(f"📋 使用配置: {settings.from_email}")
        print(f"   IMAP: {settings.imap_host}:{settings.imap_port}")
        print(f"   协议: {settings.security_protocol}")

        # 直接IMAP连接
        print("\n🔌 连接IMAP服务器...")
        if settings.security_protocol == "SSL":
            mail = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port)
        else:
            mail = imaplib.IMAP4(settings.imap_host, settings.imap_port)

        print("🔑 登录中...")
        mail.login(settings.smtp_username, settings.smtp_password)
        print("✅ IMAP登录成功")

        # 列出所有文件夹
        print("\n📁 邮箱文件夹列表:")
        folders = mail.list()
        for folder in folders[1]:
            folder_name = folder.decode("utf-8")
            print(f"   {folder_name}")

        # 选择INBOX
        mail.select("INBOX")
        print("\n📨 INBOX邮件统计:")

        # 获取所有邮件数量
        _, all_messages = mail.search(None, "ALL")
        total_count = len(all_messages[0].split()) if all_messages[0] else 0
        print(f"   总邮件数: {total_count}")

        # 获取未读邮件数量
        _, unread_messages = mail.search(None, "UNSEEN")
        unread_count = len(unread_messages[0].split()) if unread_messages[0] else 0
        print(f"   未读邮件数: {unread_count}")

        # 获取今天的邮件
        today = datetime.now().strftime("%d-%b-%Y")
        _, today_messages = mail.search(None, f'SINCE "{today}"')
        today_count = len(today_messages[0].split()) if today_messages[0] else 0
        print(f"   今天的邮件: {today_count}")

        # 获取最近的邮件详情
        if unread_count > 0:
            print(f"\n📖 未读邮件详情:")
            unread_list = unread_messages[0].split()
            for i, msg_num in enumerate(unread_list[-5:], 1):  # 最多显示5封
                _, msg_data = mail.fetch(msg_num, "(RFC822)")
                email_message = email.message_from_bytes(msg_data[0][1])

                # 解析邮件信息
                subject = ""
                if email_message["Subject"]:
                    subject, encoding = decode_header(email_message["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding or "utf-8")

                sender = email_message.get("From", "")
                date = email_message.get("Date", "")

                print(f"   {i}. {subject[:50]}...")
                print(f"      发件人: {sender}")
                print(f"      时间: {date}")

        elif today_count > 0:
            print(f"\n📅 今天的邮件详情:")
            today_list = today_messages[0].split()
            for i, msg_num in enumerate(today_list[-3:], 1):  # 最多显示3封
                _, msg_data = mail.fetch(msg_num, "(RFC822)")
                email_message = email.message_from_bytes(msg_data[0][1])

                # 解析邮件信息
                subject = ""
                if email_message["Subject"]:
                    subject, encoding = decode_header(email_message["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding or "utf-8")

                sender = email_message.get("From", "")
                date = email_message.get("Date", "")

                print(f"   {i}. {subject[:50]}...")
                print(f"      发件人: {sender}")
                print(f"      时间: {date}")

        else:
            print("   📭 没有找到未读邮件或今天的邮件")

        mail.logout()
        await processor.close()

    except Exception as e:
        print(f"❌ IMAP连接测试失败: {e}")
        import traceback

        traceback.print_exc()


async def test_email_processor_fetch():
    """测试EmailProcessor的邮件获取逻辑"""
    print("\n🔄 测试EmailProcessor邮件获取")
    print("-" * 35)

    try:
        processor = EmailProcessor(
            db_config=Config.get_db_config(), ai_config=Config.get_ai_config()
        )
        await processor.initialize()

        tenant_id = "33723dd6-cf28-4dab-975c-f883f5389d04"
        settings_list = await processor.get_smtp_settings(tenant_id)

        if not settings_list:
            print("❌ 没有找到SMTP设置")
            await processor.close()
            return

        settings = settings_list[0]
        print(f"📋 使用配置: {settings.from_email}")

        # 调用EmailProcessor的邮件获取方法
        emails = await processor.fetch_emails(settings)

        print(f"📨 EmailProcessor获取到 {len(emails)} 封邮件")

        if emails:
            print("\n📋 邮件列表:")
            for i, email_data in enumerate(emails, 1):
                print(f"   {i}. {email_data['subject'][:50]}...")
                print(f"      发件人: {email_data['sender_email']}")
                print(f"      接收时间: {email_data['received_at']}")
        else:
            print("   📭 没有获取到新邮件")
            print("   原因可能是:")
            print("   - 邮件已被之前的处理标记为已读")
            print("   - 没有新的未读邮件")
            print("   - IMAP搜索条件限制")

        await processor.close()

    except Exception as e:
        print(f"❌ EmailProcessor测试失败: {e}")
        import traceback

        traceback.print_exc()


async def suggest_test_email():
    """建议测试邮件内容"""
    print("\n💡 测试邮件建议")
    print("-" * 20)

    print("为了测试邮件分类功能，建议发送以下类型的测试邮件:")

    print("\n📋 项目相关邮件示例:")
    print("主题: Python开发案件のご紹介")
    print("内容:")
    print(
        """
    お疲れ様です。
    
    下記の案件についてご紹介させていただきます。
    
    【案件概要】
    ・案件名：ECサイトのバックエンド開発
    ・技術：Python, Django, PostgreSQL
    ・期間：2024年6月〜長期
    ・場所：東京都渋谷区（リモート可）
    ・単価：70万円/月
    
    ご興味がございましたら、ご連絡ください。
    """
    )

    print("\n👨‍💻 エンジニア関連邮件示例:")
    print("主题: エンジニアのご紹介")
    print("内容:")
    print(
        """
    お疲れ様です。
    
    弊社所属のエンジニアをご紹介いたします。
    
    【エンジニア情報】
    ・氏名：田中太郎
    ・経験：Java 5年、Python 3年
    ・希望単価：60-70万円
    ・稼働：即日可能
    
    詳細な経歴書を添付いたします。
    """
    )


async def main():
    print("📧 邮件接收调试工具")
    print("分析为什么测试邮件没有被接收")
    print("=" * 50)

    # 1. 检查数据库中的邮件记录
    await check_processed_emails()

    # 2. 直接测试IMAP连接
    await test_direct_imap_connection()

    # 3. 测试EmailProcessor的获取逻辑
    await test_email_processor_fetch()

    # 4. 提供测试建议
    await suggest_test_email()

    print("\n" + "=" * 50)
    print("🔍 调试总结:")
    print("1. 如果IMAP连接正常但EmailProcessor没获取到邮件:")
    print("   - 邮件可能已被标记为已读")
    print("   - 尝试发送新的测试邮件")
    print("2. 如果没有未读邮件:")
    print("   - 检查邮件是否在垃圾邮件文件夹")
    print("   - 确认邮件已送达邮箱")
    print("3. 测试建议:")
    print("   - 发送包含项目或工程师关键词的邮件")
    print("   - 等待几分钟后再运行调度器")


if __name__ == "__main__":
    asyncio.run(main())
