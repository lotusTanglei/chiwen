from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from dataclasses import dataclass
from getpass import getuser


def _now_ts() -> int:
    return int(time.time())


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _write_text(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


@dataclass(frozen=True)
class LockInfo:
    created_at: int
    ttl_seconds: int
    pid: int
    user: str
    host: str

    @property
    def expires_at(self) -> int:
        return self.created_at + self.ttl_seconds

    def to_dict(self) -> dict:
        return {
            "created_at": self.created_at,
            "ttl_seconds": self.ttl_seconds,
            "pid": self.pid,
            "user": self.user,
            "host": self.host,
            "expires_at": self.expires_at,
        }


def default_lock_info(ttl_seconds: int) -> LockInfo:
    return LockInfo(
        created_at=_now_ts(),
        ttl_seconds=ttl_seconds,
        pid=os.getpid(),
        user=getuser(),
        host=socket.gethostname(),
    )


def lock_file_path(docs_dir: str) -> str:
    return os.path.join(docs_dir, ".chiwen.lock")


def state_file_path(docs_dir: str) -> str:
    return os.path.join(docs_dir, ".chiwen.state.json")


def _load_lock(path: str) -> LockInfo | None:
    try:
        data = json.loads(_read_text(path))
        return LockInfo(
            created_at=int(data.get("created_at", 0)),
            ttl_seconds=int(data.get("ttl_seconds", 0)),
            pid=int(data.get("pid", 0)),
            user=str(data.get("user", "")),
            host=str(data.get("host", "")),
        )
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return None


def acquire_docs_lock(docs_dir: str, ttl_seconds: int = 600) -> LockInfo:
    os.makedirs(docs_dir, exist_ok=True)
    path = lock_file_path(docs_dir)

    existing = _load_lock(path)
    if existing is not None and _now_ts() >= existing.expires_at:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass

    info = default_lock_info(ttl_seconds)
    payload = json.dumps(info.to_dict(), ensure_ascii=False)

    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(path, flags)
        try:
            os.write(fd, payload.encode("utf-8"))
        finally:
            os.close(fd)
        return info
    except FileExistsError:
        existing = _load_lock(path)
        if existing is None:
            raise RuntimeError(f"文档锁冲突：{path}")
        raise RuntimeError(
            "文档锁冲突：已有进程正在写入 .docs/，"
            f"user={existing.user}, host={existing.host}, pid={existing.pid}, "
            f"expires_at={existing.expires_at}"
        )


def release_docs_lock(docs_dir: str) -> None:
    path = lock_file_path(docs_dir)
    try:
        os.remove(path)
    except FileNotFoundError:
        return


def read_state(docs_dir: str) -> dict | None:
    path = state_file_path(docs_dir)
    try:
        return json.loads(_read_text(path))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def write_state(docs_dir: str, state: dict) -> None:
    path = state_file_path(docs_dir)
    _write_text(path, json.dumps(state, ensure_ascii=False, indent=2) + "\n")


def _run_git(args: list[str], cwd: str) -> str:
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git 命令失败")
    return result.stdout.strip()


def is_git_repo(project_root: str) -> bool:
    try:
        _run_git(["rev-parse", "--is-inside-work-tree"], project_root)
        return True
    except Exception:
        return False


def git_head(project_root: str) -> str:
    return _run_git(["rev-parse", "HEAD"], project_root)


def git_docs_dirty(project_root: str) -> bool:
    out = _run_git(["status", "--porcelain", "--", ".docs"], project_root)
    return bool(out.strip())

