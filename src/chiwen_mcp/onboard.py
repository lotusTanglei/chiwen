"""chiwen Knowledge Kit - Onboard 命令逻辑

实现成员加入项目引导功能：获取用户名、创建个人空间、输出阅读清单。
"""

from __future__ import annotations

import os
import subprocess


def get_username() -> str | None:
    """获取当前用户名。

    优先级：git config user.name → 环境变量 USER → 环境变量 USERNAME。
    全部获取失败时返回 None。

    Returns:
        用户名字符串，或 None（全部获取失败时）
    """
    # 1. 尝试 git config user.name
    try:
        result = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # 2. 尝试环境变量 USER
    user = os.environ.get("USER", "").strip()
    if user:
        return user

    # 3. 尝试环境变量 USERNAME
    username = os.environ.get("USERNAME", "").strip()
    if username:
        return username

    return None


def generate_notepad(username: str) -> str:
    """生成 notepad.md 私人笔记模板。

    此文件不进 git，仅本机可见。

    Args:
        username: 用户名

    Returns:
        notepad.md 的 Markdown 内容
    """
    return f"""# @{username} 私人笔记

> 此文件仅存在于本机，不会提交到 Git。
> 用于记录个人想法、临时笔记、调试记录等。

## 笔记

"""


def generate_cache(username: str) -> str:
    """生成 cache.md 共享偏好模板。

    此文件进 git，包含工作风格、当前关注点、已知盲区三个章节。

    Args:
        username: 用户名

    Returns:
        cache.md 的 Markdown 内容
    """
    return f"""# @{username} 工作偏好

## 工作风格
- 偏好沟通方式：
- 时区/工作时间：

## 当前关注点
- 目前在处理的模块：

## 已知的项目盲区
- （哪些区域不熟悉）
"""


def get_reading_list() -> list[dict[str, str]]:
    """返回项目阅读清单。

    按顺序引导阅读：0_INDEX.md → 1_ARCHITECTURE.md → 2_CAPABILITIES.md。

    Returns:
        阅读清单列表，每项包含 file（文件名）和 description（说明）
    """
    return [
        {"file": "0_INDEX.md", "description": "了解文档体系全貌"},
        {"file": "1_ARCHITECTURE.md", "description": "了解项目架构和模块"},
        {"file": "2_CAPABILITIES.md", "description": "了解当前系统能力"},
    ]


def onboard(project_root: str, username: str | None = None, overwrite: bool = False) -> dict:
    """主函数：创建个人空间并输出阅读清单。

    流程：
    1. 获取用户名（如未提供）
    2. 检查个人目录是否已存在
    3. 创建个人空间（notepad.md + cache.md）
    4. 返回阅读清单

    Args:
        project_root: 项目根目录路径
        username: 可选，指定用户名。为 None 时自动获取。

    Returns:
        包含执行结果的字典：
        - success: 是否成功
        - username: 使用的用户名
        - user_dir: 创建的个人目录路径
        - files_created: 创建的文件列表
        - reading_list: 项目阅读清单
        - message: 结果消息
        - already_exists: 个人目录是否已存在（仅当已存在时出现）
    """
    # 1. 获取用户名
    if username is None:
        username = get_username()

    if not username:
        return {
            "success": False,
            "message": "无法获取用户名。请通过 git config user.name 设置，或手动指定用户名。",
            "username": None,
            "user_dir": None,
            "files_created": [],
            "reading_list": [],
        }

    # 2. 检查个人目录是否已存在
    user_dir = os.path.join(project_root, ".docs", "users", f"@{username}")

    existed_before = os.path.isdir(user_dir)
    if existed_before and not overwrite:
        return {
            "success": False,
            "message": f"个人目录已存在：{user_dir}",
            "username": username,
            "user_dir": user_dir,
            "files_created": [],
            "reading_list": get_reading_list(),
            "already_exists": True,
        }

    # 3. 创建个人空间
    os.makedirs(user_dir, exist_ok=True)

    files_created = []

    notepad_path = os.path.join(user_dir, "notepad.md")
    with open(notepad_path, "w", encoding="utf-8") as f:
        f.write(generate_notepad(username))
    files_created.append(notepad_path)

    cache_path = os.path.join(user_dir, "cache.md")
    with open(cache_path, "w", encoding="utf-8") as f:
        f.write(generate_cache(username))
    files_created.append(cache_path)

    # 4. 返回结果
    return {
        "success": True,
        "message": f"已为 @{username} 创建个人空间",
        "username": username,
        "user_dir": user_dir,
        "files_created": files_created,
        "reading_list": get_reading_list(),
        "already_exists": existed_before,
    }
