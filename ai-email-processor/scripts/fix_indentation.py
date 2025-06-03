#!/usr/bin/env python3
# fix_indentation.py
"""自动修复 email_processor.py 中的缩进问题"""

import re
import os


def fix_email_processor_indentation():
    """修复 EmailProcessor 类中方法的缩进问题"""

    file_path = "src/email_processor.py"

    if not os.path.exists(file_path):
        print(f"❌ 文件不存在: {file_path}")
        return False

    # 备份原文件
    backup_path = file_path + ".backup"
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✅ 已创建备份文件: {backup_path}")

    # 需要修正缩进的方法名列表
    methods_to_fix = [
        "_parse_email",
        "extract_project_info",
        "save_email_to_db",
        "save_project",
        "save_engineer_from_resume",
        "extract_engineer_info",
        "save_engineer",
        "process_emails_for_tenant",
    ]

    lines = content.split("\n")
    fixed_lines = []
    in_class = False
    current_method = None

    for i, line in enumerate(lines):
        # 检测是否进入 EmailProcessor 类
        if re.match(r"^class EmailProcessor:", line):
            in_class = True
            fixed_lines.append(line)
            continue

        # 检测是否离开类（下一个顶级定义）
        if (
            in_class
            and re.match(r"^class |^def |^async def ", line)
            and not line.startswith("    ")
        ):
            in_class = False
            fixed_lines.append(line)
            continue

        # 如果在类内部，检查是否是需要修复的方法
        if in_class:
            # 检查是否是需要修复的方法定义
            for method_name in methods_to_fix:
                if re.match(rf"^async def {method_name}\(", line):
                    # 添加正确的缩进
                    fixed_lines.append("    " + line)
                    current_method = method_name
                    print(f"🔧 修复方法: {method_name}")
                    break
            else:
                # 检查是否是普通的 def 方法（需要修复缩进）
                if re.match(r"^def [_a-zA-Z]", line):
                    fixed_lines.append("    " + line)
                    current_method = "method"
                    break
                else:
                    # 如果当前在修复的方法内部，确保正确缩进
                    if current_method and not line.strip() == "":
                        if not line.startswith("    "):
                            # 为方法内容添加缩进
                            if line.startswith(" "):
                                # 已有一些缩进，调整为正确缩进
                                fixed_lines.append("    " + line)
                            else:
                                # 没有缩进，添加正确缩进
                                fixed_lines.append("        " + line)
                        else:
                            fixed_lines.append(line)
                    else:
                        fixed_lines.append(line)

                    # 检查是否结束当前方法
                    if line.strip() == "" and current_method:
                        # 空行可能表示方法结束
                        pass
                    elif re.match(r"^async def |^def |^class ", line):
                        current_method = None
        else:
            fixed_lines.append(line)

    # 写入修复后的内容
    fixed_content = "\n".join(fixed_lines)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(fixed_content)

    print(f"✅ 已修复文件: {file_path}")
    print(f"📋 如果修复有问题，可以恢复备份: mv {backup_path} {file_path}")

    return True


def manual_fix_guide():
    """提供手动修复指南"""
    print("\n" + "=" * 60)
    print("📖 手动修复指南")
    print("=" * 60)
    print("如果自动修复脚本有问题，请手动修复以下方法的缩进：")
    print("\n在 EmailProcessor 类中，以下方法需要正确的缩进（4个空格）：")

    methods = [
        "_parse_email",
        "extract_project_info",
        "save_email_to_db",
        "save_project",
        "save_engineer_from_resume",
        "extract_engineer_info",
        "save_engineer",
        "process_emails_for_tenant",
    ]

    for method in methods:
        print(f"  ✓ async def {method}(self, ...)")

    print(f"\n修复步骤：")
    print(f"1. 找到每个方法定义行")
    print(f"2. 确保方法定义前有4个空格的缩进")
    print(f"3. 确保方法内容有8个空格的缩进")
    print(f"4. 保存文件并重新运行程序")


if __name__ == "__main__":
    print("🔧 EmailProcessor 缩进修复工具")
    print("=" * 50)

    success = fix_email_processor_indentation()

    if success:
        print("\n🎉 修复完成！现在可以重新运行程序了。")
        print("\n运行测试:")
        print("  python scripts/test_email_processor.py")
        print("  python scripts/run_scheduler.py")
    else:
        manual_fix_guide()

    print("\n" + "=" * 50)
