"""
Git 同步服务 - 定时将本地数据目录推送到远程 Git 仓库
"""
import subprocess
import os
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class GitSyncService:
    """Git同步服务"""

    def __init__(self):
        self.settings = get_settings()
        self.repo_path = Path(self.settings.git_repo_path).resolve()
        self.remote_url = self.settings.git_remote_url
        self.branch = self.settings.git_branch
        self.user_name = self.settings.git_user_name
        self.user_email = self.settings.git_user_email

    def _run_git(self, *args) -> Dict[str, Any]:
        """执行git命令"""
        cmd = ["git", "-C", str(self.repo_path)] + list(args)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                encoding="utf-8",
                errors="replace"
            )
            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip()
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "returncode": -1, "stdout": "", "stderr": "命令超时（60秒）"}
        except Exception as e:
            return {"success": False, "returncode": -1, "stdout": "", "stderr": str(e)}

    def _ensure_git_initialized(self) -> Dict[str, Any]:
        """确保Git仓库已初始化"""
        # 检查是否已是git仓库
        check = self._run_git("rev-parse", "--is-inside-work-tree")
        if check["success"]:
            return {"success": True, "message": "Git仓库已存在"}

        # 初始化
        self.repo_path.mkdir(parents=True, exist_ok=True)
        init = self._run_git("init")
        if not init["success"]:
            return {"success": False, "message": f"Git初始化失败: {init['stderr']}"}

        # 配置用户信息
        self._run_git("config", "user.name", self.user_name)
        self._run_git("config", "user.email", self.user_email)

        # 如果有远程地址，添加remote
        if self.remote_url:
            remote_check = self._run_git("remote", "get-url", "origin")
            if not remote_check["success"]:
                self._run_git("remote", "add", "origin", self.remote_url)

        return {"success": True, "message": "Git仓库初始化完成"}

    def sync(self) -> Dict[str, Any]:
        """
        执行一次同步：add → commit → push
        
        Returns:
            {"success": bool, "message": str, "details": {...}}
        """
        # Step 0: 检查配置
        if not self.remote_url:
            return {"success": False, "message": "未配置 GIT_REMOTE_URL"}

        # Step 1: 确保仓库已初始化
        init_result = self._ensure_git_initialized()
        if not init_result["success"]:
            return init_result

        # Step 2: git add
        add_result = self._run_git("add", "-A")
        if not add_result["success"]:
            return {"success": False, "message": f"git add 失败: {add_result['stderr']}"}

        # Step 3: 检查是否有变更
        status = self._run_git("status", "--porcelain")
        if not status["success"]:
            return {"success": False, "message": f"git status 失败: {status['stderr']}"}

        if not status["stdout"]:
            return {"success": True, "message": "没有变更，跳过同步"}

        # 统计变更文件数
        changed_files = len(status["stdout"].strip().split("\n"))

        # Step 4: git commit
        commit_msg = self.settings.git_commit_message
        if not commit_msg:
            commit_msg = f"auto sync: {datetime.now().strftime('%Y-%m-%d %H:%M')} ({changed_files} files changed)"

        commit_result = self._run_git("commit", "-m", commit_msg)
        if not commit_result["success"]:
            # 可能是没有可提交的内容（已被add但没有实际变更）
            if "nothing to commit" in commit_result["stdout"] or "nothing to commit" in commit_result["stderr"]:
                return {"success": True, "message": "没有实际变更，跳过同步"}
            return {"success": False, "message": f"git commit 失败: {commit_result['stderr']}"}

        # Step 5: git push
        push_args = ["push", "origin", self.branch]
        # 如果是首次推送，使用 --set-upstream
        branch_exists = self._run_git("rev-parse", "--verify", f"refs/remotes/origin/{self.branch}")
        if not branch_exists["success"]:
            push_args.insert(2, "--set-upstream")

        push_result = self._run_git(*push_args)
        if not push_result["success"]:
            return {
                "success": False,
                "message": f"git push 失败: {push_result['stderr']}",
                "details": {
                    "commit": commit_msg,
                    "changed_files": changed_files
                }
            }

        return {
            "success": True,
            "message": f"同步成功: {changed_files}个文件已推送到 {self.branch}",
            "details": {
                "commit": commit_msg,
                "changed_files": changed_files,
                "branch": self.branch
            }
        }

    def get_status(self) -> Dict[str, Any]:
        """获取当前Git状态"""
        check = self._run_git("rev-parse", "--is-inside-work-tree")
        if not check["success"]:
            return {
                "initialized": False,
                "remote_url": self.remote_url,
                "branch": self.branch
            }

        # 获取当前分支
        branch = self._run_git("branch", "--show-current")
        current_branch = branch["stdout"] if branch["success"] else "unknown"

        # 获取远程地址
        remote = self._run_git("remote", "get-url", "origin")
        remote_url = remote["stdout"] if remote["success"] else "none"

        # 获取未提交的变更数
        status = self._run_git("status", "--porcelain")
        uncommitted = len(status["stdout"].strip().split("\n")) if status["stdout"] else 0

        # 获取未推送的提交数
        unpushed = self._run_git("log", f"origin/{current_branch}..HEAD", "--oneline")
        unpushed_count = len(unpushed["stdout"].strip().split("\n")) if unpushed["stdout"] else 0

        return {
            "initialized": True,
            "remote_url": remote_url,
            "branch": current_branch,
            "uncommitted_changes": uncommitted,
            "unpushed_commits": unpushed_count
        }
