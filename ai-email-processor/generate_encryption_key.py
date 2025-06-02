#!/usr/bin/env python3
# generate_encryption_key.py
"""生成加密密钥的工具脚本"""

import secrets
import string
import base64
import hashlib
from cryptography.fernet import Fernet


def generate_simple_key(length=64):
    """生成简单的随机字符串密钥"""
    characters = string.ascii_letters + string.digits + "!@#$%^&*()_+-="
    return "".join(secrets.choice(characters) for _ in range(length))


def generate_fernet_key():
    """生成符合Fernet要求的密钥"""
    return Fernet.generate_key().decode()


def generate_hash_based_key(passphrase):
    """基于用户提供的密码短语生成密钥"""
    return base64.urlsafe_b64encode(
        hashlib.sha256(passphrase.encode()).digest()
    ).decode()


def main():
    print("=== AI Email Processor 加密密钥生成器 ===\n")

    print("选择密钥生成方式:")
    print("1. 自动生成随机密钥 (推荐)")
    print("2. 生成Fernet标准密钥")
    print("3. 基于密码短语生成")
    print("4. 生成多个密钥供选择")

    choice = input("\n请选择 (1-4): ").strip()

    if choice == "1":
        key = generate_simple_key()
        print(f"\n生成的加密密钥:")
        print(f"ENCRYPTION_KEY={key}")

    elif choice == "2":
        key = generate_fernet_key()
        print(f"\n生成的Fernet密钥:")
        print(f"ENCRYPTION_KEY={key}")

    elif choice == "3":
        passphrase = input("\n请输入密码短语 (至少20个字符): ")
        if len(passphrase) < 20:
            print("❌ 密码短语太短，请使用至少20个字符")
            return
        key = generate_hash_based_key(passphrase)
        print(f"\n基于密码短语生成的密钥:")
        print(f"ENCRYPTION_KEY={key}")

    elif choice == "4":
        print("\n生成多个密钥供选择:")
        for i in range(5):
            key = generate_simple_key()
            print(f"{i+1}. ENCRYPTION_KEY={key}")

    else:
        print("无效选择")
        return

    print("\n" + "=" * 60)
    print("⚠️  重要提醒:")
    print("1. 请将生成的密钥保存到 .env 文件中")
    print("2. 密钥一旦设置，请勿随意更改")
    print("3. 更改密钥会导致已加密的密码无法解密")
    print("4. 请妥善保管此密钥，不要泄露给他人")
    print("5. 建议定期备份密钥到安全位置")
    print("=" * 60)


if __name__ == "__main__":
    main()
