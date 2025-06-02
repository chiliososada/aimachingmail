# test_db_connection.py
"""数据库连接测试脚本"""

import sys
import os
import asyncio
import asyncpg
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


async def test_db_connection():
    """测试 Supabase PostgreSQL 连接"""
    try:
        # 数据库连接参数
        connection_params = {
            "host": os.getenv("DB_HOST"),
            "port": int(os.getenv("DB_PORT", 5432)),
            "database": os.getenv("DB_NAME"),
            "user": os.getenv("DB_USER"),
            "password": os.getenv("DB_PASSWORD"),
        }

        print("🔄 尝试连接 Supabase 数据库...")
        print(f'📍 主机: {connection_params["host"]}')
        print(f'📍 端口: {connection_params["port"]}')
        print(f'📍 数据库: {connection_params["database"]}')
        print(f'📍 用户: {connection_params["user"]}')
        print("-" * 50)

        # 检查必要参数
        if not all(
            [
                connection_params["host"],
                connection_params["database"],
                connection_params["user"],
                connection_params["password"],
            ]
        ):
            print("❌ 缺少必要的数据库连接参数")
            print("请检查 .env 文件中的以下设置:")
            print("- DB_HOST")
            print("- DB_NAME")
            print("- DB_USER")
            print("- DB_PASSWORD")
            return False

        # 尝试连接
        conn = await asyncpg.connect(**connection_params)
        print("✅ Supabase 数据库连接成功!")

        # 测试基本查询
        version = await conn.fetchval("SELECT version()")
        print(f"📊 数据库版本: {version[:60]}...")

        # 检查当前数据库大小
        db_size = await conn.fetchval(
            """
            SELECT pg_size_pretty(pg_database_size(current_database()))
        """
        )
        print(f"💾 数据库大小: {db_size}")

        # 列出现有表
        tables = await conn.fetch(
            """
            SELECT schemaname, tablename 
            FROM pg_tables 
            WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
            ORDER BY schemaname, tablename
        """
        )

        if tables:
            print(f"📋 现有数据表 ({len(tables)} 个):")
            for table in tables[:15]:  # 只显示前15个表
                print(f'   - {table["schemaname"]}.{table["tablename"]}')
            if len(tables) > 15:
                print(f"   ... 还有 {len(tables) - 15} 个表")
        else:
            print("📋 暂无用户数据表")

        # 检查连接状态
        connection_info = await conn.fetchrow(
            """
            SELECT 
                current_database() as database,
                current_user as user,
                inet_server_addr() as server_ip,
                inet_server_port() as server_port
        """
        )
        print(f'🔗 连接信息: {connection_info["user"]}@{connection_info["database"]}')

        await conn.close()
        print("✅ 数据库连接测试完成")
        return True

    except asyncpg.InvalidPasswordError:
        print("❌ 密码错误")
        print("💡 请检查 Supabase 项目的数据库密码")
        return False
    except asyncpg.InvalidCatalogNameError:
        print("❌ 数据库名称错误")
        print("💡 请检查数据库名称设置")
        return False
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        print("💡 请检查:")
        print("   1. 网络连接是否正常")
        print("   2. Supabase 服务是否正常")
        print("   3. 防火墙设置")
        print("   4. .env 文件配置")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Supabase PostgreSQL 连接测试")
    print("=" * 60)

    # 检查 .env 文件是否存在
    if not os.path.exists(".env"):
        print("❌ .env 文件不存在")
        print("请先创建 .env 文件并配置数据库连接信息")
        sys.exit(1)

    # 运行测试
    result = asyncio.run(test_db_connection())

    print("=" * 60)
    if result:
        print("🎉 测试成功! 数据库连接正常")
    else:
        print("💥 测试失败! 请检查配置")
        sys.exit(1)
