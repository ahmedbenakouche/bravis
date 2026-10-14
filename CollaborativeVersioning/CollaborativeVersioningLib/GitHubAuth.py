"""Talk to GitHub through the Git and GitHub CLI (gh) already on the machine."""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import stat
import subprocess
import threading
import time
from typing import Any

GITHUB_HOST = "github.com"
WORKSPACE_FOLDER_NAME = "CollaborativeVersioning"
_wait_callback = None


def set_wait_callback(callback) -> None:
    """Called while Git/GitHub CLI is running so the UI can keep a busy animation alive."""
    global _wait_callback
    _wait_callback = callback


def _pump_wait() -> None:
    callback = _wait_callback
    if callback is not None:
        callback()


def default_workspace_dir() -> str:
    """Fixed clone location — clinicians are not asked to pick a folder."""
    return os.path.join(os.path.expanduser("~"), "Documents", WORKSPACE_FOLDER_NAME)


def local_project_dir(full_name: str) -> str:
    owner, _, repo = full_name.partition("/")
    if not owner or not repo:
        raise GitHubAuthError("Invalid project name: %s" % full_name)
    return os.path.join(default_workspace_dir(), owner, repo)


def sanitize_repo_name(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", (name or "").strip())
    slug = slug.strip(".-")
    if not slug:
        raise GitHubAuthError("Project name must contain letters or numbers.")
    return slug[:100]


class GitHubAuthError(RuntimeError):
    pass


class GitHubNotSignedInError(GitHubAuthError):
    pass


class GitHubMissingDeletePermissionError(GitHubAuthError):
    pass


def _windows_create_no_window():
    if os.name != "nt":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def _which(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    if os.name != "nt":
        return None
    extra = [
        os.path.expandvars(r"%ProgramFiles%\GitHub CLI\gh.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\GitHub CLI\gh.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\GitHub CLI\gh.exe"),
        os.path.expandvars(r"%ProgramFiles%\Git\cmd\git.exe"),
        os.path.expandvars(r"%ProgramFiles%\Git\bin\git.exe"),
    ]
    for path in extra:
        if path and os.path.isfile(path):
            if name.lower() in os.path.basename(path).lower():
                return path
    return None


def find_git() -> str | None:
    return _which("git")


def find_gh() -> str | None:
    return _which("gh")


def missing_tools_message() -> str:
    return (
        "Git and GitHub CLI (gh) must be installed on this computer.\n\n"
        "A technician can install them once, for example in PowerShell:\n"
        "  winget install --id Git.Git -e --source winget\n"
        "  winget install --id GitHub.cli -e --source winget\n\n"
        "Close and reopen 3D Slicer afterwards."
    )


def not_signed_in_message() -> str:
    return "GitHub CLI is not signed in on this computer."


def open_login_window() -> None:
    """Open `gh auth login --web` in a visible console and return immediately."""
    gh = find_gh()
    if not gh:
        raise GitHubAuthError(missing_tools_message())
    args = [
        gh,
        "auth",
        "login",
        "--hostname",
        GITHUB_HOST,
        "--git-protocol",
        "https",
        "--web",
        "--clipboard",
        "--skip-ssh-key",
        "--scopes",
        "repo,delete_repo",
    ]
    if os.name == "nt":
        command = 'cmd.exe /c start "GitHub sign-in" ' + subprocess.list2cmdline(args)
        subprocess.Popen(command, shell=True)
        return
    subprocess.Popen(args, start_new_session=True)


def _run_captured(
    command: list[str],
    timeout: int,
    cwd: str | None,
    timeout_label: str,
    stdin_text: str | None = None,
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["GH_PAGER"] = ""
    env["GIT_PAGER"] = ""
    env["GH_PROMPT_DISABLED"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    if env_extra:
        env.update(env_extra)
    stdin = subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL
    try:
        process = subprocess.Popen(
            command,
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
            env=env,
            **_windows_create_no_window(),
        )
    except OSError as error:
        raise GitHubAuthError("Could not run %s: %s" % (timeout_label, error)) from error
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    def _drain(stream, chunks: list[str]) -> None:
        try:
            chunks.append(stream.read() or "")
        except Exception:
            chunks.append("")

    readers = [
        threading.Thread(target=_drain, args=(process.stdout, stdout_chunks)),
        threading.Thread(target=_drain, args=(process.stderr, stderr_chunks)),
    ]
    for reader in readers:
        reader.daemon = True
        reader.start()
    if stdin_text is not None:
        try:
            process.stdin.write(stdin_text)
            process.stdin.close()
        except OSError:
            pass
    start = time.time()
    while True:
        remaining = timeout - (time.time() - start)
        if remaining <= 0:
            process.kill()
            for reader in readers:
                reader.join(timeout=1)
            raise GitHubAuthError("%s timed out." % timeout_label)
        if process.poll() is not None:
            for reader in readers:
                reader.join(timeout=2)
            return subprocess.CompletedProcess(
                command,
                process.returncode,
                "".join(stdout_chunks),
                "".join(stderr_chunks),
            )
        _pump_wait()
        time.sleep(0.05)


def _run_gh(
    args: list[str],
    timeout: int = 60,
    cwd: str | None = None,
    stdin_text: str | None = None,
) -> subprocess.CompletedProcess:
    gh = find_gh()
    if not gh:
        raise GitHubAuthError(missing_tools_message())
    return _run_captured([gh, *args], timeout, cwd, "GitHub CLI", stdin_text=stdin_text)


def _run_gh_blocking(args: list[str], timeout: int = 25) -> subprocess.CompletedProcess:
    """Hard timeout, no Qt event pumping. Use for short API calls started from a dialog."""
    gh = find_gh()
    if not gh:
        raise GitHubAuthError(missing_tools_message())
    env = os.environ.copy()
    env["GH_PAGER"] = ""
    env["GIT_PAGER"] = ""
    env["GH_PROMPT_DISABLED"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        return subprocess.run(
            [gh, *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            env=env,
            **_windows_create_no_window(),
        )
    except subprocess.TimeoutExpired as error:
        raise GitHubAuthError("GitHub CLI timed out.") from error


def ensure_tools() -> None:
    if not find_git() or not find_gh():
        raise GitHubAuthError(missing_tools_message())
    git_probe = subprocess.run(
        [find_git(), "--version"],
        capture_output=True,
        text=True,
        timeout=20,
        **_windows_create_no_window(),
    )
    if git_probe.returncode != 0:
        raise GitHubAuthError(missing_tools_message())
    gh_probe = _run_gh(["--version"], timeout=20)
    if gh_probe.returncode != 0:
        raise GitHubAuthError(missing_tools_message())


def token_scopes() -> list[str] | None:
    """Return OAuth scopes for the current GitHub CLI token, if they can be read."""
    result = _run_gh(["api", "-i", "user"], timeout=30)
    text = "%s\n%s" % (result.stdout or "", result.stderr or "")
    for line in text.splitlines():
        if line.lower().startswith("x-oauth-scopes:"):
            raw = line.split(":", 1)[1]
            return [part.strip().strip("'\"") for part in raw.split(",") if part.strip()]
    status = _run_gh(["auth", "status"], timeout=30)
    status_text = "%s\n%s" % (status.stdout or "", status.stderr or "")
    for line in status_text.splitlines():
        if "token scopes:" in line.lower():
            raw = line.split(":", 1)[1]
            return [part.strip().strip("'\"") for part in raw.split(",") if part.strip()]
    return None


def has_delete_repo_scope() -> bool | None:
    scopes = token_scopes()
    if scopes is None:
        return None
    return "delete_repo" in scopes


def _is_missing_delete_scope(detail: str) -> bool:
    lowered = (detail or "").lower()
    return "delete_repo" in lowered or "must have admin rights to repository" in lowered


def open_delete_permission_window() -> None:
    """Open `gh auth refresh` in a visible console so delete_repo can be granted."""
    gh = find_gh()
    if not gh:
        raise GitHubAuthError(missing_tools_message())
    args = [
        gh,
        "auth",
        "refresh",
        "--hostname",
        GITHUB_HOST,
        "--scopes",
        "repo,delete_repo",
    ]
    if os.name == "nt":
        command = 'cmd.exe /c start "GitHub delete permission" ' + subprocess.list2cmdline(args)
        subprocess.Popen(command, shell=True)
        return
    subprocess.Popen(args, start_new_session=True)


def current_login() -> str | None:
    result = _run_gh(["api", "user"], timeout=30)
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return None
    login = payload.get("login")
    return str(login) if login else None


def logout_github_cli(login: str | None = None) -> None:
    """Sign GitHub CLI out of github.com so another account can sign in."""
    args = ["auth", "logout", "--hostname", GITHUB_HOST]
    if login:
        args.extend(["--user", str(login)])
    result = _run_gh([*args, "--yes"], timeout=40, stdin_text="Y\n")
    combined = "%s\n%s" % (result.stdout or "", result.stderr or "")
    if result.returncode != 0 and "unknown flag" in combined.lower():
        result = _run_gh(args, timeout=40, stdin_text="Y\n")
    if result.returncode != 0:
        result = _run_gh(args, timeout=40, stdin_text="Y\n")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise GitHubAuthError("Could not sign out of GitHub.\n%s" % detail[:400])


def list_accessible_repos(login: str) -> list[dict[str, Any]]:
    result = _run_gh(
        ["api", "--paginate", "user/repos?affiliation=owner,collaborator&per_page=100"],
        timeout=90,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise GitHubAuthError("Could not list GitHub repositories.\n%s" % detail[:400])
    try:
        chunk = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as error:
        raise GitHubAuthError("GitHub CLI returned invalid repository data.") from error
    if not isinstance(chunk, list):
        raise GitHubAuthError("Unexpected repository list from GitHub CLI.")
    repos = []
    for item in chunk:
        if not isinstance(item, dict):
            continue
        permissions = item.get("permissions") or {}
        owner_login = (item.get("owner") or {}).get("login", "")
        full_name = item.get("full_name") or ""
        if not full_name:
            continue
        repos.append(
            {
                "full_name": full_name,
                "private": bool(item.get("private")),
                "can_push": bool(permissions.get("push")),
                "role": "owner" if owner_login == login else "collaborator",
            }
        )
    repos.sort(key=lambda item: item["full_name"].lower())
    return repos


def _is_under_workspace(path: str) -> bool:
    workspace = os.path.abspath(default_workspace_dir())
    target = os.path.abspath(path)
    try:
        return os.path.commonpath([workspace, target]) == workspace
    except ValueError:
        return False


def _make_tree_writable(path: str) -> None:
    if not os.path.exists(path):
        return
    for root, dirs, files in os.walk(path):
        for name in dirs + files:
            target = os.path.join(root, name)
            try:
                os.chmod(target, stat.S_IWRITE | stat.S_IREAD)
            except OSError:
                pass
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass


def _rmtree_force(path: str) -> None:
    def _on_error(func, target, _exc):
        try:
            os.chmod(target, stat.S_IWRITE | stat.S_IREAD)
            func(target)
        except OSError:
            pass

    try:
        shutil.rmtree(path, onexc=_on_error)
    except TypeError:
        shutil.rmtree(path, onerror=lambda func, target, _exc: _on_error(func, target, None))


def remove_local_project_dir(path: str) -> None:
    """Delete a local project folder. Windows git files are often read-only."""
    if not path or not os.path.exists(path):
        return
    if not _is_under_workspace(path):
        raise GitHubAuthError("Could not remove the local folder.")
    last_error = None
    for _attempt in range(6):
        try:
            _make_tree_writable(path)
            if os.path.isdir(path):
                _rmtree_force(path)
            elif os.path.exists(path):
                os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
                os.remove(path)
            if not os.path.exists(path):
                return
        except OSError as error:
            last_error = error
        time.sleep(0.4)
    detail = str(last_error) if last_error else path
    raise GitHubAuthError("Could not remove the local folder:\n%s" % detail)


def github_project_exists(full_name: str) -> bool:
    result = _run_gh(["repo", "view", full_name, "--json", "name"], timeout=30)
    return result.returncode == 0


def create_private_repository(name: str, description: str = "") -> dict[str, Any]:
    """Create a private GitHub repo under the signed-in account and clone it locally."""
    ensure_tools()
    login = current_login()
    if not login:
        raise GitHubNotSignedInError(not_signed_in_message())
    slug = sanitize_repo_name(name)
    full_name = "%s/%s" % (login, slug)
    parent_dir = os.path.join(default_workspace_dir(), login)
    os.makedirs(parent_dir, exist_ok=True)
    dest = local_project_dir(full_name)
    if github_project_exists(full_name):
        raise GitHubAuthError("A project named %s already exists." % full_name)
    if os.path.exists(dest):
        remove_local_project_dir(dest)
    args = ["repo", "create", slug, "--private", "--clone"]
    if description.strip():
        args.extend(["--description", description.strip()])
    result = _run_gh(args, timeout=120, cwd=parent_dir)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise GitHubAuthError("Could not create the project.\n%s" % detail[:500])
    if not os.path.isdir(dest):
        raise GitHubAuthError("The project was created on GitHub but was not cloned to:\n%s" % dest)
    _configure_repo_identity(dest, login)
    repos = list_accessible_repos(login)
    created = next((item for item in repos if item.get("full_name") == full_name), None)
    if created is None:
        created = {
            "full_name": full_name,
            "private": True,
            "can_push": True,
            "role": "owner",
        }
        repos.append(created)
        repos.sort(key=lambda item: item["full_name"].lower())
    created["local_path"] = dest
    return created


def _configure_repo_identity(repo_dir: str, login: str) -> None:
    git = find_git()
    if not git:
        return
    email = "%s@users.noreply.github.com" % login
    for key, value in (("user.name", login), ("user.email", email)):
        subprocess.run(
            [git, "config", key, value],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=20,
            **_windows_create_no_window(),
        )


def _run_git(
    args: list[str],
    cwd: str,
    timeout: int = 120,
    stdin_text: str | None = None,
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    git = find_git()
    if not git:
        raise GitHubAuthError(missing_tools_message())
    return _run_captured(
        [git, *args],
        timeout,
        cwd,
        "Git",
        stdin_text=stdin_text,
        env_extra=env_extra,
    )


def connect_session() -> dict[str, Any]:
    ensure_tools()
    login = current_login()
    if not login:
        raise GitHubNotSignedInError(not_signed_in_message())
    return {"login": login, "repos": list_accessible_repos(login)}


def _stage_and_commit(repo_dir: str, message: str, fail_prefix: str) -> None:
    login = current_login()
    if login:
        _configure_repo_identity(repo_dir, login)
    add = _run_git(["add", "-A"], cwd=repo_dir)
    if add.returncode != 0:
        raise GitHubAuthError("Could not add project files.\n%s" % (add.stderr or add.stdout or "")[:400])
    status = _run_git(["status", "--porcelain"], cwd=repo_dir, timeout=30)
    if status.returncode == 0 and not (status.stdout or "").strip():
        raise GitHubAuthError("No new changes to save.")
    commit = _run_git(["commit", "-m", message], cwd=repo_dir)
    if commit.returncode != 0:
        detail = (commit.stderr or commit.stdout or "").strip()
        if "nothing to commit" in detail.lower():
            raise GitHubAuthError("No new changes to save.")
        raise GitHubAuthError("%s\n%s" % (fail_prefix, detail[:400]))


def _commit_path_is_volume(path: str) -> bool:
    name = os.path.basename((path or "").replace("\\", "/")).lower()
    return "_volume" in name or "_reference" in name


def _list_commit_paths(repo_dir: str, sha: str) -> list[str]:
    result = _run_git(["ls-tree", "--name-only", "-r", sha], cwd=repo_dir, timeout=30)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise GitHubAuthError("Could not switch version.\n%s" % detail[:400])
    paths = []
    for line in (result.stdout or "").splitlines():
        path = line.strip().replace("\\", "/")
        if path:
            paths.append(path)
    return paths


def head_can_update_shared_project(repo_dir: str) -> bool:
    """True when Share can add this computer's versions onto the shared project line."""
    head = _git_rev_parse(repo_dir, "HEAD")
    if not head:
        return False
    origin = _git_rev_parse(repo_dir, "origin/main")
    if not origin:
        return True
    return _is_ancestor(repo_dir, origin, head)


def work_is_on_review_branch(repo_dir: str) -> bool:
    return _current_branch_name(repo_dir).startswith("cv-review/")


def commit_local_version(repo_dir: str, message: str) -> None:
    """Commit all files in the local project folder. Does not publish them."""
    _stage_and_commit(repo_dir, message, "Could not save the version.")


def git_branch_for_history_lane(lane: str) -> str:
    """Map a version-tree lane name to the local git branch that owns it."""
    name = str(lane or "").strip()
    if not name or name.lower() == "main":
        return "main"
    return review_branch_for(name)


def checkout_local_version(repo_dir: str, sha: str, lane: str = "main") -> None:
    """Point HEAD at this version and sync the full worktree (Switch).

    Uses one git reset --hard. Must always move to the target sha — even when
    that commit is an ancestor of current HEAD (switching to an older version).
    """
    if not repo_dir or not os.path.isdir(os.path.join(repo_dir, ".git")):
        raise GitHubAuthError("Open the project first.")
    if not sha:
        raise GitHubAuthError("Could not switch version.")
    branch = git_branch_for_history_lane(lane)
    head = _git_rev_parse(repo_dir, "HEAD")
    current = _current_branch_name(repo_dir)
    if head == sha and current == branch:
        return
    _checkout_branch_at(repo_dir, branch, sha)


def _share_failure_message(detail: str) -> str:
    lower = (detail or "").lower()
    if (
        "non-fast-forward" in lower
        or "failed to push some refs" in lower
        or "updates were rejected" in lower
    ):
        return (
            "Could not share. The shared project has versions that are not on this computer.\n\n"
            "Open Compare with shared first (bell / notifications), resolve the differences, "
            "then share again."
        )
    if "permission" in lower or "403" in lower or "write access" in lower:
        return "Could not share. This project is read-only for your account."
    return "Could not share the project yet.\n%s" % (detail or "")[:400]


def share_local_versions(repo_dir: str) -> None:
    """Publish saved local versions onto the shared project. Does not create a new version."""
    if not repo_dir or not os.path.isdir(os.path.join(repo_dir, ".git")):
        raise GitHubAuthError("Open the project first.")
    origin = _run_git(["rev-parse", "--verify", "--quiet", "origin/main"], cwd=repo_dir, timeout=30)
    if origin.returncode == 0 and not _unpushed_commit_shas(repo_dir):
        raise GitHubAuthError("No new versions to share.")
    login = current_login()
    if login:
        _configure_repo_identity(repo_dir, login)
    if origin.returncode == 0 and not head_can_update_shared_project(repo_dir):
        _merge_head_into_shared_project(repo_dir, login or "owner")
        return
    push = _run_git(
        ["push", "-u", "origin", "HEAD:refs/heads/main"],
        cwd=repo_dir,
        timeout=180,
    )
    if push.returncode != 0:
        raise GitHubAuthError(_share_failure_message((push.stderr or push.stdout or "").strip()))
    head = _git_rev_parse(repo_dir, "HEAD")
    if head:
        _run_git(["update-ref", "refs/remotes/origin/main", head], cwd=repo_dir, timeout=20)
    _publish_current_review_line(repo_dir, login)
    _return_head_to_main(repo_dir)


def _merge_head_into_shared_project(repo_dir: str, login: str) -> None:
    """Merge this computer's line into the shared project. No pull request.

    The shared project keeps its history as the first parent. The files at the
    merge are this computer's current version (the work that was just saved).
    """
    origin = _git_rev_parse(repo_dir, "origin/main")
    head = _git_rev_parse(repo_dir, "HEAD")
    if not origin or not head:
        raise GitHubAuthError("Could not share the project yet.")
    tree = _run_git(["rev-parse", "%s^{tree}" % head], cwd=repo_dir, timeout=20)
    tree_sha = (tree.stdout or "").strip()
    if tree.returncode != 0 or not tree_sha:
        raise GitHubAuthError("Could not share the project yet.")
    name = normalize_github_username(login) or "owner"
    commit = _run_git(
        [
            "commit-tree",
            tree_sha,
            "-p",
            origin,
            "-p",
            head,
            "-m",
            "Accept version from %s" % name,
        ],
        cwd=repo_dir,
        timeout=30,
    )
    merge_sha = (commit.stdout or "").strip()
    if commit.returncode != 0 or not merge_sha:
        detail = (commit.stderr or commit.stdout or "").strip()
        raise GitHubAuthError("Could not share the project yet.\n%s" % detail[:400])
    _run_git(["update-ref", "refs/heads/main", merge_sha], cwd=repo_dir, timeout=20)
    push = _run_git(
        ["push", "origin", "%s:refs/heads/main" % merge_sha],
        cwd=repo_dir,
        timeout=180,
    )
    if push.returncode != 0:
        raise GitHubAuthError(_share_failure_message((push.stderr or push.stdout or "").strip()))
    _run_git(["update-ref", "refs/remotes/origin/main", merge_sha], cwd=repo_dir, timeout=20)
    _publish_current_review_line(repo_dir, name)
    _return_head_to_main(repo_dir)


def _publish_current_review_line(repo_dir: str, login: str) -> None:
    """Publish this computer's side branch so it appears on GitHub. Share only."""
    name = normalize_github_username(login or "")
    if not name:
        return
    current = _current_branch_name(repo_dir)
    if not current.startswith("cv-review/"):
        return
    head = _git_rev_parse(repo_dir, "HEAD")
    if not head:
        return
    branch = review_branch_for(name)
    push = _run_git(
        ["push", "origin", "HEAD:refs/heads/%s" % branch],
        cwd=repo_dir,
        timeout=180,
    )
    if push.returncode != 0:
        raise GitHubAuthError(_share_failure_message((push.stderr or push.stdout or "").strip()))
    _run_git(["update-ref", "refs/remotes/origin/%s" % branch, head], cwd=repo_dir, timeout=20)


def _return_head_to_main(repo_dir: str) -> None:
    """After Share, work from main again so Open can update the shared project."""
    main = _git_rev_parse(repo_dir, "refs/heads/main") or _git_rev_parse(repo_dir, "origin/main")
    if not main:
        return
    if _current_branch_name(repo_dir) != "main":
        _point_head_at(repo_dir, "main", main)
    _run_git(["branch", "--set-upstream-to=origin/main", "main"], cwd=repo_dir, timeout=20)


def people_access_for(full_name: str, login: str | None = None) -> str:
    """senior = share now; junior = needs review. Owner is always senior."""
    owner, _repo = _split_project_name(full_name)
    name = normalize_github_username(login or current_login() or "")
    if not name or name.lower() == owner.lower():
        return PEOPLE_ACCESS_SENIOR
    return _people_access_map(full_name).get(name.lower()) or PEOPLE_ACCESS_JUNIOR


def review_lane_slug(login: str) -> str:
    """Version-tree column for this person. Matches the history lane name."""
    name = normalize_github_username(login) or ""
    if not name:
        return ""
    if name.lower() == "main":
        return "reviewer-main"
    return name


def review_branch_for(login: str) -> str:
    name = normalize_github_username(login) or "colleague"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-") or "colleague"
    return "cv-review/%s" % safe


def publish_review_branch(repo_dir: str) -> None:
    """Share current versions on this person's branch beside main. Does not merge into main."""
    if not repo_dir or not os.path.isdir(os.path.join(repo_dir, ".git")):
        raise GitHubAuthError("Open the project first.")
    origin = _run_git(["rev-parse", "--verify", "--quiet", "origin/main"], cwd=repo_dir, timeout=30)
    if origin.returncode == 0 and not _unpushed_commit_shas(repo_dir):
        raise GitHubAuthError("No new versions to share.")
    login = current_login()
    if not login:
        raise GitHubNotSignedInError(not_signed_in_message())
    _configure_repo_identity(repo_dir, login)
    branch = review_branch_for(login)
    head = _git_rev_parse(repo_dir, "HEAD")
    if not head:
        raise GitHubAuthError("Could not share the project yet.")
    remote_tip = _git_rev_parse(repo_dir, "refs/remotes/origin/%s" % branch) or _git_rev_parse(
        repo_dir, "refs/heads/%s" % branch
    )
    if _current_branch_name(repo_dir) != branch:
        if (
            remote_tip
            and remote_tip != head
            and not _is_ancestor(repo_dir, remote_tip, head)
        ):
            raise GitHubAuthError(
                "Could not share on your line.\n\n"
                "Switch to a version on your line first, then Save, then Share again."
            )
        _point_head_at(repo_dir, branch, head)
    elif (
        remote_tip
        and remote_tip != head
        and not _is_ancestor(repo_dir, remote_tip, head)
    ):
        raise GitHubAuthError(
            "Could not share on your line.\n\n"
            "Switch to a version on your line first, then Save, then Share again."
        )
    push = _run_git(
        ["push", "origin", "HEAD:refs/heads/%s" % branch],
        cwd=repo_dir,
        timeout=180,
    )
    if push.returncode != 0:
        raise GitHubAuthError(_share_failure_message((push.stderr or push.stdout or "").strip()))
    _run_git(["update-ref", "refs/remotes/origin/%s" % branch, head], cwd=repo_dir, timeout=20)
    origin_main = _git_rev_parse(repo_dir, "origin/main")
    if origin_main:
        _run_git(["update-ref", "refs/heads/main", origin_main], cwd=repo_dir, timeout=20)


def submit_review_line(full_name: str) -> str:
    """Open a review for this person's already shared line. Does not push."""
    login = current_login()
    if not login:
        raise GitHubNotSignedInError(not_signed_in_message())
    branch = review_branch_for(login)
    owner, repo = _split_project_name(full_name)
    existing = _run_gh(
        ["api", "repos/%s/%s/git/ref/heads/%s" % (owner, repo, branch)],
        timeout=30,
    )
    if existing.returncode != 0:
        raise GitHubAuthError("Share your line first.")
    title = "Share request from %s" % login
    body = "A colleague sent a version for review in 3D Slicer."
    created = _run_gh(
        [
            "pr",
            "create",
            "--repo",
            full_name,
            "--base",
            "main",
            "--head",
            branch,
            "--title",
            title,
            "--body",
            body,
        ],
        timeout=60,
    )
    if created.returncode == 0:
        return "sent"
    detail = (created.stderr or created.stdout or "").strip()
    lower = detail.lower()
    if "already exists" in lower or "already a pull request" in lower:
        return "updated"
    raise GitHubAuthError("Could not send the version for review.\n%s" % detail[:400])


def find_open_review_request(full_name: str, login: str) -> dict[str, Any] | None:
    """Open review for this person's line, if they have submitted one."""
    name = normalize_github_username(login)
    if not name or not full_name:
        return None
    branch = review_branch_for(name)
    result = _run_gh(
        [
            "pr",
            "list",
            "--repo",
            full_name,
            "--state",
            "open",
            "--limit",
            "30",
            "--json",
            "number,headRefName,title",
        ],
        timeout=40,
    )
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, list):
        return None
    title_key = "share request from %s" % name.lower()
    fallback = None
    for item in payload:
        if not isinstance(item, dict) or item.get("number") is None:
            continue
        head = str(item.get("headRefName") or "").strip()
        title = str(item.get("title") or "").strip().lower()
        if head.lower() == branch.lower():
            return {
                "number": item.get("number"),
                "full_name": full_name,
                "author": name,
                "branch": head or branch,
            }
        if title == title_key and fallback is None:
            fallback = {
                "number": item.get("number"),
                "full_name": full_name,
                "author": name,
                "branch": head or branch,
            }
    return fallback


def fetch_share_request_sha(full_name: str, branch: str) -> tuple[str, str]:
    """Resolve a review tip from the local clone. No network fetch.

    For now the clone is expected to be up to date via Open (reload + reconnect +
    open). Live history refresh can replace that later.
    """
    dest = local_project_dir(full_name)
    if not os.path.isdir(os.path.join(dest, ".git")):
        raise GitHubAuthError("Open the project first.")
    ref = (branch or "").strip()
    if not ref:
        raise GitHubAuthError("Could not open the version to review.")
    value = (
        _git_rev_parse(dest, "refs/remotes/origin/%s" % ref)
        or _git_rev_parse(dest, "origin/%s" % ref)
        or _git_rev_parse(dest, "refs/heads/%s" % ref)
    )
    if not value:
        raise GitHubAuthError(
            "Could not find this review line locally.\n\n"
            "Open the shared project first, then try again."
        )
    return dest, value


def _review_login_from_ref(ref: str) -> str:
    text = (ref or "").replace("\\", "/").strip()
    marker = "cv-review/"
    if marker not in text:
        return ""
    login = text.split(marker, 1)[-1].strip().strip("/")
    return normalize_github_username(login.split("/")[0] if login else "")


def _history_lane_slug(login: str) -> str:
    return review_lane_slug(login) or "colleague"


def _git_rev_parse(repo_dir: str, ref: str) -> str:
    if not ref:
        return ""
    result = _run_git(["rev-parse", "--verify", "--quiet", ref], cwd=repo_dir, timeout=30)
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def _current_branch_name(repo_dir: str) -> str:
    result = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir, timeout=20)
    name = (result.stdout or "").strip()
    if result.returncode != 0 or not name or name == "HEAD":
        return ""
    return name


def _is_ancestor(repo_dir: str, ancestor: str, descendant: str) -> bool:
    if not ancestor or not descendant:
        return False
    result = _run_git(
        ["merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repo_dir,
        timeout=30,
    )
    return result.returncode == 0


def _point_head_at(repo_dir: str, branch: str, sha: str) -> None:
    """Move HEAD/branch to sha without updating worktree files (reset --mixed)."""
    current = _current_branch_name(repo_dir)
    if current == branch:
        reset = _run_git(["reset", "--mixed", sha], cwd=repo_dir, timeout=30)
        if reset.returncode != 0:
            detail = (reset.stderr or reset.stdout or "").strip()
            raise GitHubAuthError("Could not update the local project.\n%s" % detail[:400])
        return
    created = _run_git(["branch", "-f", branch, sha], cwd=repo_dir, timeout=30)
    if created.returncode != 0:
        detail = (created.stderr or created.stdout or "").strip()
        raise GitHubAuthError("Could not update the local project.\n%s" % detail[:400])
    pointed = _run_git(
        ["symbolic-ref", "HEAD", "refs/heads/%s" % branch],
        cwd=repo_dir,
        timeout=20,
    )
    if pointed.returncode != 0:
        detail = (pointed.stderr or pointed.stdout or "").strip()
        raise GitHubAuthError("Could not update the local project.\n%s" % detail[:400])
    reset = _run_git(["reset", "--mixed", sha], cwd=repo_dir, timeout=30)
    if reset.returncode != 0:
        detail = (reset.stderr or reset.stdout or "").strip()
        raise GitHubAuthError("Could not update the local project.\n%s" % detail[:400])


def _checkout_branch_at(repo_dir: str, branch: str, sha: str) -> None:
    """Move HEAD/branch to sha and sync the full worktree (reset --hard)."""
    current = _current_branch_name(repo_dir)
    if current != branch:
        created = _run_git(["branch", "-f", branch, sha], cwd=repo_dir, timeout=30)
        if created.returncode != 0:
            detail = (created.stderr or created.stdout or "").strip()
            raise GitHubAuthError("Could not update the local project.\n%s" % detail[:400])
        pointed = _run_git(
            ["symbolic-ref", "HEAD", "refs/heads/%s" % branch],
            cwd=repo_dir,
            timeout=20,
        )
        if pointed.returncode != 0:
            detail = (pointed.stderr or pointed.stdout or "").strip()
            raise GitHubAuthError("Could not update the local project.\n%s" % detail[:400])
    reset = _run_git(["reset", "--hard", sha], cwd=repo_dir, timeout=180)
    if reset.returncode != 0:
        detail = (reset.stderr or reset.stdout or "").strip()
        raise GitHubAuthError("Could not update the local project.\n%s" % detail[:400])


def _restore_non_volume_worktree(repo_dir: str, sha: str) -> None:
    paths = [path for path in _list_commit_paths(repo_dir, sha) if not _commit_path_is_volume(path)]
    if not paths:
        return
    restored = _run_git(["checkout", sha, "--", *paths], cwd=repo_dir, timeout=60)
    if restored.returncode != 0:
        detail = (restored.stderr or restored.stdout or "").strip()
        raise GitHubAuthError("Could not update the local project.\n%s" % detail[:400])


def _ensure_github_branch(full_name: str, branch: str, sha: str) -> None:
    """Recreate a review line on GitHub if Accept/Decline removed the name."""
    if not full_name or not branch or not sha:
        return
    owner, repo = _split_project_name(full_name)
    existing = _run_gh(
        ["api", "repos/%s/%s/git/ref/heads/%s" % (owner, repo, branch)],
        timeout=30,
    )
    if existing.returncode == 0:
        return
    created = _run_gh(
        [
            "api",
            "-X",
            "POST",
            "repos/%s/%s/git/refs" % (owner, repo),
            "-f",
            "ref=refs/heads/%s" % branch,
            "-f",
            "sha=%s" % sha,
        ],
        timeout=40,
    )
    if created.returncode == 0:
        return
    detail = (created.stderr or created.stdout or "").strip().lower()
    if "already exists" in detail or "reference already exists" in detail:
        return


def _share_request_head(full_name: str, number) -> tuple[str, str]:
    result = _run_gh(
        [
            "pr",
            "view",
            str(number),
            "--repo",
            full_name,
            "--json",
            "headRefName,headRefOid",
        ],
        timeout=30,
    )
    if result.returncode != 0:
        return "", ""
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return "", ""
    if not isinstance(payload, dict):
        return "", ""
    branch = str(payload.get("headRefName") or "").strip()
    sha = str(payload.get("headRefOid") or "").strip()
    return branch, sha


def accept_share_request(full_name: str, branch: str, number) -> str:
    """Merge the reviewed line into the shared project. Keep that line's versions.

    Same merge style as Put on main: the junior's files become the shared tip,
    with main and the review tip as parents (no GitHub conflict check).

    Uses the local clone as already updated by Open — no git fetch here.
    """
    dest, sha = fetch_share_request_sha(full_name, branch)
    login = _review_login_from_ref(branch) or "colleague"
    accepter = current_login()
    if accepter:
        _configure_repo_identity(dest, accepter)
    origin = _git_rev_parse(dest, "origin/main") or _git_rev_parse(dest, "refs/heads/main")
    head = sha
    if not origin or not head:
        raise GitHubAuthError(
            "Could not accept the version.\n\n"
            "Open the shared project first, then try again."
        )
    if origin != head:
        tree = _run_git(["rev-parse", "%s^{tree}" % head], cwd=dest, timeout=20)
        tree_sha = (tree.stdout or "").strip()
        if tree.returncode != 0 or not tree_sha:
            raise GitHubAuthError("Could not accept the version.")
        commit = _run_git(
            [
                "commit-tree",
                tree_sha,
                "-p",
                origin,
                "-p",
                head,
                "-m",
                "Accept version from %s" % login,
            ],
            cwd=dest,
            timeout=30,
        )
        merge_sha = (commit.stdout or "").strip()
        if commit.returncode != 0 or not merge_sha:
            detail = (commit.stderr or commit.stdout or "").strip()
            raise GitHubAuthError("Could not accept the version.\n%s" % detail[:400])
        push = _run_git(
            ["push", "origin", "%s:refs/heads/main" % merge_sha],
            cwd=dest,
            timeout=180,
        )
        if push.returncode != 0:
            raise GitHubAuthError(_share_failure_message((push.stderr or push.stdout or "").strip()))
        _run_git(["update-ref", "refs/remotes/origin/main", merge_sha], cwd=dest, timeout=20)
        _run_git(["update-ref", "refs/heads/main", merge_sha], cwd=dest, timeout=20)
    if number not in (None, ""):
        closed = _run_gh(
            [
                "pr",
                "close",
                str(number),
                "--repo",
                full_name,
                "--comment",
                "Accepted in Collaborative Versioning.",
            ],
            timeout=40,
        )
        if closed.returncode != 0:
            detail = (closed.stderr or closed.stdout or "").strip().lower()
            if "already" not in detail and "not found" not in detail and "merged" not in detail:
                # Main already has the version; ignore a stuck review request label.
                pass
    try:
        _ensure_github_branch(full_name, branch, sha)
    except (GitHubAuthError, OSError, ValueError):
        pass
    # Local main refs already match what we pushed — no fetch needed.
    _run_git(["reset", "--hard", "refs/heads/main"], cwd=dest, timeout=180)
    return dest


def _declined_shas_path(repo_dir: str) -> str:
    return os.path.join(repo_dir, ".git", "cv-declined-shas")


def _load_declined_shas(repo_dir: str) -> set[str]:
    try:
        with open(_declined_shas_path(repo_dir), encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return set()
    if not isinstance(raw, list):
        return set()
    return {str(item).strip() for item in raw if str(item).strip()}


def _remember_declined_shas(repo_dir: str, shas) -> None:
    if not repo_dir or not os.path.isdir(os.path.join(repo_dir, ".git")):
        return
    current = _load_declined_shas(repo_dir)
    current.update(str(sha).strip() for sha in (shas or []) if str(sha).strip())
    try:
        with open(_declined_shas_path(repo_dir), "w", encoding="utf-8") as handle:
            json.dump(sorted(current), handle)
    except OSError:
        return


def _unique_commits_not_on_main(repo_dir: str, tip: str) -> set[str]:
    if not tip:
        return set()
    result = _run_git(
        ["log", "--format=%H", tip, "--not", "origin/main"],
        cwd=repo_dir,
        timeout=60,
    )
    shas = {line.strip() for line in (result.stdout or "").splitlines() if line.strip()}
    shas.add(tip)
    return shas


def decline_share_request(full_name: str, number, branch: str = "") -> None:
    """Close the review request but keep the colleague's versions."""
    head_branch, head_sha = _share_request_head(full_name, number)
    keep_branch = (branch or head_branch or "").strip()
    result = _run_gh(
        [
            "pr",
            "close",
            str(number),
            "--repo",
            full_name,
        ],
        timeout=40,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        lower = detail.lower()
        if "already" not in lower and "not found" not in lower:
            raise GitHubAuthError("Could not decline the version.\n%s" % detail[:400])
    if keep_branch and head_sha:
        try:
            _ensure_github_branch(full_name, keep_branch, head_sha)
        except (GitHubAuthError, OSError, ValueError):
            pass
    dest = local_project_dir(full_name)
    remembered = {head_sha} if head_sha else set()
    if os.path.isdir(os.path.join(dest, ".git")) and head_sha:
        remembered.update(_unique_commits_not_on_main(dest, head_sha))
    _remember_declined_shas(dest, remembered)


def commit_and_push(repo_dir: str, message: str) -> None:
    """Commit all files in the local project folder and publish them."""
    _stage_and_commit(repo_dir, message, "Could not save the first version.")
    _run_git(["branch", "-M", "main"], cwd=repo_dir)
    push = _run_git(["push", "-u", "origin", "main"], cwd=repo_dir, timeout=180)
    if push.returncode != 0:
        raise GitHubAuthError(
            "Could not share the project yet.\n%s" % (push.stderr or push.stdout or "").strip()[:400]
        )


def _format_git_date(iso: str) -> str:
    text = (iso or "").replace("T", " ")
    if len(text) >= 16:
        return text[:16]
    return text.strip()


def _unpushed_commit_shas(repo_dir: str) -> set[str]:
    origin = _run_git(["rev-parse", "--verify", "--quiet", "origin/main"], cwd=repo_dir, timeout=30)
    if origin.returncode != 0:
        return set()
    result = _run_git(["log", "origin/main..HEAD", "--format=%H"], cwd=repo_dir, timeout=60)
    if result.returncode != 0:
        return set()
    return {line.strip() for line in (result.stdout or "").splitlines() if line.strip()}


def inspect_local_project(full_name: str) -> dict[str, Any]:
    """Look at the local copy without changing it."""
    dest = local_project_dir(full_name)
    git_dir = os.path.join(dest, ".git")
    if not os.path.isdir(git_dir):
        return {"path": dest, "exists": False, "unshared_count": 0}
    return {
        "path": dest,
        "exists": True,
        "unshared_count": len(_unpushed_commit_shas(dest)),
    }


def fetch_remote_updates(repo_dir: str) -> None:
    """Fetch remote refs into .git only. Does not change HEAD or the worktree."""
    if not repo_dir or not os.path.isdir(os.path.join(repo_dir, ".git")):
        raise GitHubAuthError("Open the project first.")
    fetch = _run_git(["fetch", "origin"], cwd=repo_dir, timeout=180)
    if fetch.returncode != 0:
        detail = (fetch.stderr or fetch.stdout or "").strip()
        raise GitHubAuthError("Could not get the latest shared versions.\n%s" % detail[:400])


def _update_local_from_origin(repo_dir: str) -> None:
    """Update main from GitHub even if this computer is on a review line with no tracking."""
    fetch_remote_updates(repo_dir)
    origin_main = _git_rev_parse(repo_dir, "origin/main")
    if not origin_main:
        raise GitHubAuthError("Could not update the local project.")
    current = _current_branch_name(repo_dir)
    local_main = _git_rev_parse(repo_dir, "refs/heads/main")
    if current == "main":
        pull = _run_git(["pull", "--ff-only", "origin", "main"], cwd=repo_dir, timeout=180)
        if pull.returncode != 0:
            pull = _run_git(["pull", "origin", "main"], cwd=repo_dir, timeout=180)
        if pull.returncode != 0:
            detail = (pull.stderr or pull.stdout or "").strip()
            raise GitHubAuthError("Could not update the local project.\n%s" % detail[:400])
        _run_git(["branch", "--set-upstream-to=origin/main", "main"], cwd=repo_dir, timeout=20)
        return
    if not local_main or local_main == origin_main or _is_ancestor(repo_dir, local_main, origin_main):
        _run_git(["update-ref", "refs/heads/main", origin_main], cwd=repo_dir, timeout=20)
        target = origin_main
    elif _is_ancestor(repo_dir, origin_main, local_main):
        target = local_main
    else:
        raise GitHubAuthError(
            "Could not update the local project. The shared project has versions that are not on this computer.\n\n"
            "Open Compare with shared first (bell / notifications) and resolve the differences."
        )
    _checkout_branch_at(repo_dir, "main", target)
    _run_git(["branch", "--set-upstream-to=origin/main", "main"], cwd=repo_dir, timeout=20)


def open_or_update_local_project(full_name: str, mode: str = "update") -> str:
    """Clone the GitHub project locally, or open/update the existing local copy."""
    ensure_tools()
    login = current_login()
    if not login:
        raise GitHubNotSignedInError(not_signed_in_message())
    dest = local_project_dir(full_name)
    parent = os.path.dirname(dest)
    os.makedirs(parent, exist_ok=True)
    git_dir = os.path.join(dest, ".git")
    if os.path.isdir(git_dir) and mode == "local":
        _configure_repo_identity(dest, login)
        return dest
    if os.path.isdir(git_dir) and mode != "replace":
        _update_local_from_origin(dest)
        _configure_repo_identity(dest, login)
        return dest
    if os.path.exists(dest):
        remove_local_project_dir(dest)
    result = _run_gh(["repo", "clone", full_name, dest], timeout=300)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise GitHubAuthError("Could not open the project.\n%s" % detail[:500])
    if not os.path.isdir(dest):
        raise GitHubAuthError("The project was not copied to:\n%s" % dest)
    _configure_repo_identity(dest, login)
    return dest


def _history_refs(repo_dir: str) -> list[str]:
    result = _run_git(
        [
            "for-each-ref",
            "--format=%(refname)",
            "refs/heads/cv-review",
            "refs/remotes/origin/cv-review",
        ],
        cwd=repo_dir,
        timeout=30,
    )
    if result.returncode != 0:
        return []
    refs = []
    for line in (result.stdout or "").splitlines():
        ref = line.strip()
        if ref:
            refs.append(ref)
    return refs


def _review_tips(
    repo_dir: str,
    *,
    local_only: bool = False,
    remote_only: bool = False,
) -> dict[str, list[str]]:
    """Tips for cv-review lanes. Optionally restrict to local heads or origin remotes."""
    tips: dict[str, list[str]] = {}
    for ref in _history_refs(repo_dir):
        if local_only and not ref.startswith("refs/heads/cv-review"):
            continue
        if remote_only and not ref.startswith("refs/remotes/origin/cv-review"):
            continue
        login = _review_login_from_ref(ref)
        if not login:
            continue
        sha = _git_rev_parse(repo_dir, ref)
        if not sha:
            continue
        bucket = tips.setdefault(login.lower(), [])
        if sha not in bucket:
            bucket.append(sha)
    return tips


def _first_parent_chain(commit_by_sha: dict[str, dict], tip: str) -> list[str]:
    chain = []
    seen = set()
    current = tip
    while current and current not in seen:
        seen.add(current)
        chain.append(current)
        parents = (commit_by_sha.get(current) or {}).get("parents") or []
        current = parents[0] if parents else ""
    return chain


def _unique_side_chain(commit_by_sha: dict[str, dict], tip: str, stop: set[str]) -> list[str]:
    chain = []
    seen = set()
    current = tip
    while current and current not in seen and current not in stop:
        seen.add(current)
        chain.append(current)
        parents = (commit_by_sha.get(current) or {}).get("parents") or []
        current = parents[0] if parents else ""
    chain.reverse()
    return chain


def _history_log_refs(repo_dir: str) -> list[str]:
    refs = []
    seen = set()
    for ref in ("HEAD", "refs/heads/main", "refs/remotes/origin/main"):
        if not _git_rev_parse(repo_dir, ref):
            continue
        if ref not in seen:
            seen.add(ref)
            refs.append(ref)
    for ref in _history_refs(repo_dir):
        if ref not in seen:
            seen.add(ref)
            refs.append(ref)
    return refs


def _slug_from_merge(
    commit_by_sha: dict[str, dict],
    merge_sha: str,
    extra_sha: str,
    review_tips: dict[str, list[str]],
) -> str:
    message = str((commit_by_sha.get(merge_sha) or {}).get("message") or "")
    found = re.search(r"Accept version from\s+(\S+)", message, re.I)
    if found:
        return _history_lane_slug(found.group(1))
    found = re.search(r"cv-review/([A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?)", message)
    if found:
        return _history_lane_slug(found.group(1))
    extra_chain = set(_first_parent_chain(commit_by_sha, extra_sha))
    for login, tips in review_tips.items():
        if isinstance(tips, str):
            tips = [tips]
        for tip in tips:
            if extra_sha in set(_first_parent_chain(commit_by_sha, tip)) or extra_chain.intersection(
                _first_parent_chain(commit_by_sha, tip)
            ):
                return _history_lane_slug(login)
    author = str((commit_by_sha.get(extra_sha) or {}).get("author") or "colleague")
    return _history_lane_slug(re.sub(r"[^A-Za-z0-9]+", "-", author).strip("-") or "colleague")


def _lane_status(
    branch: str,
    sha: str,
    unpushed: set[str],
    accepted_ids: set[str],
    declined_shas: set[str],
    version_id: str,
) -> str:
    if branch == "main":
        return "local" if sha in unpushed else "pushed"
    if version_id in accepted_ids:
        return "Accepted"
    if sha in declined_shas:
        return "Declined"
    return "To review"


def build_project_history_model(
    commit_by_sha: dict[str, dict[str, Any]],
    main_tip: str,
    head_sha: str,
    review_tips: dict[str, list[str]],
    unpushed: set[str],
    declined_shas: set[str] | None = None,
) -> dict[str, Any]:
    """Turn Git commits + review tips into version specs (DAG)."""
    empty = {
        "commit_history": [],
        "version_specs": [],
        "tags_by_id": {},
        "sha_by_id": {},
        "head_id": None,
    }
    if not commit_by_sha:
        return empty
    id_by_sha: dict[str, str] = {}
    specs_by_id: dict[str, dict[str, Any]] = {}
    tags: dict[str, str] = {}
    sha_by_id: dict[str, str] = {}

    def add_spec(version_id: str, sha: str, parent_id, branch: str) -> None:
        if sha in id_by_sha:
            return
        record = commit_by_sha.get(sha) or {}
        parents = record.get("parents") or []
        is_merge = branch == "main" and len(parents) > 1
        spec = {
            "id": version_id,
            "parent": parent_id,
            "branch": branch,
            "tag": version_id,
            "merge": is_merge,
        }
        id_by_sha[sha] = version_id
        specs_by_id[version_id] = spec
        tags[version_id] = version_id
        sha_by_id[version_id] = sha

    main_chain = _first_parent_chain(commit_by_sha, main_tip) if main_tip else []
    main_set = set(main_chain)
    for index, sha in enumerate(reversed(main_chain), start=1):
        record = commit_by_sha.get(sha) or {}
        parents = record.get("parents") or []
        first = parents[0] if parents else ""
        parent_id = id_by_sha.get(first)
        add_spec("main/%d" % index, sha, parent_id, "main")

    lane_shas: dict[str, list[str]] = {}

    def remember_side(slug: str, tip: str) -> None:
        if not slug or not tip:
            return
        lane_shas.setdefault(slug, []).extend(_unique_side_chain(commit_by_sha, tip, main_set))

    for login, tips in sorted(review_tips.items(), key=lambda item: item[0]):
        slug = _history_lane_slug(login)
        if isinstance(tips, str):
            tips = [tips]
        for tip in tips:
            remember_side(slug, tip)
    for merge_sha in main_chain:
        parents = (commit_by_sha.get(merge_sha) or {}).get("parents") or []
        for extra in parents[1:]:
            remember_side(_slug_from_merge(commit_by_sha, merge_sha, extra, review_tips), extra)

    for slug, shas in sorted(lane_shas.items()):
        unique = []
        seen = set()
        for sha in shas:
            if not sha or sha in seen or sha in id_by_sha:
                continue
            seen.add(sha)
            unique.append(sha)
        unique.sort(key=lambda item: str((commit_by_sha.get(item) or {}).get("date") or ""))
        for index, sha in enumerate(unique, start=1):
            record = commit_by_sha.get(sha) or {}
            parents = record.get("parents") or []
            first = parents[0] if parents else ""
            parent_id = id_by_sha.get(first)
            add_spec("%s/%d" % (slug, index), sha, parent_id, slug)

    leftover = []
    if head_sha:
        for sha in reversed(_first_parent_chain(commit_by_sha, head_sha)):
            if sha not in id_by_sha:
                leftover.append(sha)
    main_count = sum(1 for version_id in specs_by_id if version_id.startswith("main/"))
    for sha in leftover:
        record = commit_by_sha.get(sha) or {}
        parents = record.get("parents") or []
        first = parents[0] if parents else ""
        parent_id = id_by_sha.get(first)
        main_count += 1
        add_spec("main/%d" % main_count, sha, parent_id, "main")

    for extra_id in list(id_by_sha.values()):
        spec = specs_by_id.get(extra_id) or {}
        if not spec.get("merge"):
            continue
        sha = sha_by_id.get(extra_id) or ""
        parents = (commit_by_sha.get(sha) or {}).get("parents") or []
        merge_from = [id_by_sha[p] for p in parents[1:] if p in id_by_sha]
        if merge_from:
            spec["merge_from"] = merge_from

    accepted_ids = set()
    for spec in specs_by_id.values():
        if spec.get("merge"):
            accepted_ids.update(spec.get("merge_from") or [])

    history_rows = []
    for sha, version_id in id_by_sha.items():
        spec = specs_by_id[version_id]
        record = commit_by_sha.get(sha) or {}
        status = _lane_status(
            str(spec.get("branch") or "main"),
            sha,
            unpushed,
            accepted_ids,
            set(declined_shas or ()),
            version_id,
        )
        history_rows.append(
            (
                record.get("date") or "",
                version_id,
                [
                    version_id,
                    _format_git_date(str(record.get("date") or "")),
                    str(record.get("author") or ""),
                    str(record.get("message") or ""),
                    status,
                ],
            )
        )
    history_rows.sort(key=lambda item: item[0], reverse=True)
    specs = []
    seen_specs = set()
    for sha in reversed(main_chain):
        version_id = id_by_sha.get(sha)
        if version_id and version_id not in seen_specs:
            specs.append(specs_by_id[version_id])
            seen_specs.add(version_id)
    for spec in specs_by_id.values():
        if spec["id"] not in seen_specs:
            specs.append(spec)
            seen_specs.add(spec["id"])
    head_id = id_by_sha.get(head_sha) or id_by_sha.get(main_tip)
    return {
        "commit_history": [row for _date, _vid, row in history_rows],
        "version_specs": specs,
        "tags_by_id": tags,
        "sha_by_id": sha_by_id,
        "head_id": head_id,
    }


def _empty_history_model() -> dict[str, Any]:
    return {
        "commit_history": [],
        "version_specs": [],
        "tags_by_id": {},
        "sha_by_id": {},
        "head_id": None,
    }


def _read_repo_commits(repo_dir: str) -> dict[str, dict[str, Any]]:
    """Load commit metadata for history / compare views."""
    if not repo_dir or not os.path.isdir(os.path.join(repo_dir, ".git")):
        return {}
    refs = _history_log_refs(repo_dir)
    if not refs:
        return {}
    result = _run_git(
        ["log", "--parents", "--reverse", "--format=%H%x1f%P%x1f%cI%x1f%an%x1f%s", *refs],
        cwd=repo_dir,
        timeout=60,
    )
    if result.returncode != 0:
        return {}
    commit_by_sha: dict[str, dict[str, Any]] = {}
    for line in (result.stdout or "").splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f")
        if len(parts) < 5:
            continue
        sha, parent_text, iso, author, message = parts[0], parts[1], parts[2], parts[3], parts[4]
        parents = [item for item in parent_text.split() if item]
        commit_by_sha[sha] = {
            "parents": parents,
            "date": iso,
            "author": author,
            "message": message,
        }
    return commit_by_sha


_UI_SYNC_CAPS_FILE = ".cv_ui_sync_caps.json"


def _ensure_ui_sync_caps_gitignored(repo_dir: str) -> None:
    """Keep .cv_ui_sync_caps.json local — never Share/push it to GitHub."""
    if not repo_dir or not os.path.isdir(repo_dir):
        return
    gitignore = os.path.join(repo_dir, ".gitignore")
    marker = _UI_SYNC_CAPS_FILE
    try:
        existing = ""
        if os.path.isfile(gitignore):
            with open(gitignore, encoding="utf-8") as handle:
                existing = handle.read()
        lines = existing.splitlines()
        if any(line.strip() == marker for line in lines):
            return
        suffix = "" if (not existing or existing.endswith("\n")) else "\n"
        with open(gitignore, "a", encoding="utf-8") as handle:
            handle.write("%s# Collaborative Versioning — local UI only\n%s\n" % (suffix, marker))
    except OSError:
        return
    # If it was staged earlier, unstage without deleting the file.
    _run_git(["rm", "--cached", "-f", "--ignore-unmatch", marker], cwd=repo_dir, timeout=20)


def capture_remote_sync_caps(repo_dir: str) -> dict[str, Any]:
    """Snapshot origin/main + origin review tips (for Version-tree display caps)."""
    origin = _git_rev_parse(repo_dir, "origin/main") or ""
    review = {}
    for login, tips in sorted(_review_tips(repo_dir, remote_only=True).items()):
        tip = ""
        for candidate in tips:
            if candidate:
                tip = candidate
        if tip:
            review[str(login).strip().lower()] = tip
    return {"origin_main": origin, "review_tips": review}


def save_remote_sync_caps(repo_dir: str, caps: dict[str, Any] | None) -> None:
    """Persist which remote tips the Version tree is allowed to show until Update."""
    if not repo_dir or not os.path.isdir(repo_dir):
        return
    _ensure_ui_sync_caps_gitignored(repo_dir)
    path = os.path.join(repo_dir, _UI_SYNC_CAPS_FILE)
    payload = {
        "origin_main": str((caps or {}).get("origin_main") or "").strip(),
        "review_tips": dict((caps or {}).get("review_tips") or {}),
    }
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except OSError:
        pass


def load_remote_sync_caps(repo_dir: str) -> dict[str, Any] | None:
    if not repo_dir:
        return None
    path = os.path.join(repo_dir, _UI_SYNC_CAPS_FILE)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    tips = payload.get("review_tips")
    if tips is not None and not isinstance(tips, dict):
        tips = {}
    return {
        "origin_main": str(payload.get("origin_main") or "").strip(),
        "review_tips": {
            str(login).strip().lower(): str(sha).strip()
            for login, sha in (tips or {}).items()
            if str(login).strip() and str(sha).strip()
        },
    }


def _cap_remote_tip(repo_dir: str, stored: str, current: str) -> str:
    """If the user has not Validated Update, keep showing the last acknowledged tip."""
    stored = str(stored or "").strip()
    current = str(current or "").strip()
    if not stored:
        return current
    if not current or stored == current:
        return stored
    # current ahead of stored → hide newer commits until Update
    if _is_ancestor(repo_dir, stored, current):
        return stored
    return current


def derive_remote_sync_caps_from_history(
    repo_dir: str, history: dict[str, Any] | None
) -> dict[str, Any]:
    """Build UI caps from versions already shown (Version tree / Compare Local snapshot).

    Used before a Compare peek-fetch so Open does not suddenly show newer origin tips
    that were only fetched for the compare dialog.
    """
    known = _history_shas(history)
    commit_by_sha = _read_repo_commits(repo_dir)
    origin = _git_rev_parse(repo_dir, "origin/main") or ""

    def _newest_known_on_chain(tip: str) -> str:
        if not tip:
            return ""
        for sha in _first_parent_chain(commit_by_sha, tip):
            if sha in known:
                return sha
        return ""

    origin_cap = _newest_known_on_chain(origin) or origin
    review: dict[str, str] = {}
    for login, tips in sorted(_review_tips(repo_dir, remote_only=True).items()):
        current = ""
        for candidate in tips:
            if candidate:
                current = candidate
        capped = _newest_known_on_chain(current)
        if capped:
            review[str(login).strip().lower()] = capped
        elif current and current in known:
            review[str(login).strip().lower()] = current
    return {"origin_main": origin_cap, "review_tips": review}


def read_project_history(repo_dir: str, *, apply_ui_caps: bool = True) -> dict[str, Any]:
    """Read saved versions, including review lines, as a DAG.

    When ``apply_ui_caps`` is True (default for the Version tree UI), remote tips
    are capped to the last Validate Update / Take / explicit sync — so a Compare
    peek-fetch alone does not rewrite the Version tree on the next Open.
    """
    empty = _empty_history_model()
    commit_by_sha = _read_repo_commits(repo_dir)
    if not commit_by_sha:
        return empty
    origin = _git_rev_parse(repo_dir, "origin/main")
    local_main = _git_rev_parse(repo_dir, "main")
    head_sha = _git_rev_parse(repo_dir, "HEAD")
    local_tips = _review_tips(repo_dir, local_only=True)
    remote_tips = _review_tips(repo_dir, remote_only=True)
    main_tip = origin or local_main

    if apply_ui_caps:
        caps = load_remote_sync_caps(repo_dir)
        if caps:
            main_tip = (
                _cap_remote_tip(repo_dir, caps.get("origin_main") or "", origin or "")
                or local_main
            )
            stored_review = caps.get("review_tips") or {}
            capped_remote: dict[str, list[str]] = {}
            for login, tips in remote_tips.items():
                current = ""
                for candidate in tips:
                    if candidate:
                        current = candidate
                key = str(login).strip().lower()
                use = _cap_remote_tip(repo_dir, stored_review.get(key) or "", current)
                if use:
                    capped_remote[login] = [use]
            remote_tips = capped_remote

    review_tips: dict[str, list[str]] = dict(remote_tips)
    for login, tips in local_tips.items():
        bucket = review_tips.setdefault(login, [])
        for tip in tips:
            if tip and tip not in bucket:
                bucket.append(tip)

    unpushed = _unpushed_commit_shas(repo_dir)
    model = build_project_history_model(
        commit_by_sha,
        main_tip,
        head_sha,
        review_tips,
        unpushed,
        declined_shas=_load_declined_shas(repo_dir),
    )
    if not model.get("version_specs"):
        return empty
    return model


def _first_parent_merge_base(commit_by_sha: dict[str, dict], tip_a: str, tip_b: str) -> str:
    """Approximate merge-base using first-parent chains (main-line compare)."""
    if not tip_a or not tip_b:
        return ""
    a_set = set(_first_parent_chain(commit_by_sha, tip_a))
    for sha in _first_parent_chain(commit_by_sha, tip_b):
        if sha in a_set:
            return sha
    return ""


def _history_shas(model: dict[str, Any] | None) -> set[str]:
    return {str(sha) for sha in ((model or {}).get("sha_by_id") or {}).values() if sha}


def read_compare_project_histories(
    repo_dir: str,
    local_history: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build local vs shared graphs for Compare (call after fetch for the remote side).

    Does not change HEAD / worktree.

    - ``local_history``: frozen Version-tree bundle from *before* fetch (exact UI state).
      If omitted, falls back to a local-only rebuild (main/HEAD + local review heads).
    - Shared graph: ``origin/main`` + ``origin/cv-review/*`` after fetch.
    - Diff (dashed boxes): SHA set difference between the two graphs
      (e.g. hemido214/1 already in local ⇒ not marked on remote; only /2 is).
    - ``conflict``: local main tip vs origin/main diverged.
    """
    empty = _empty_history_model()
    commit_by_sha = _read_repo_commits(repo_dir)
    origin = _git_rev_parse(repo_dir, "origin/main")
    local_main = _git_rev_parse(repo_dir, "refs/heads/main")
    head_sha = _git_rev_parse(repo_dir, "HEAD")
    unpushed = _unpushed_commit_shas(repo_dir)
    declined = _load_declined_shas(repo_dir)
    local_review_tips = _review_tips(repo_dir, local_only=True)
    remote_review_tips = _review_tips(repo_dir, remote_only=True)

    remote_main_shas: set[str] = (
        set(_first_parent_chain(commit_by_sha, origin)) if origin else set()
    )
    local_main_shas: set[str] = (
        set(_first_parent_chain(commit_by_sha, local_main)) if local_main else set()
    )

    # Shared = what GitHub has now (after fetch).
    remote_model = empty
    if (origin or remote_review_tips) and commit_by_sha:
        remote_model = build_project_history_model(
            commit_by_sha,
            origin or "",
            origin or "",
            remote_review_tips,
            set(),
            declined_shas=declined,
        )

    # Local = frozen Version tree when provided (same as what the user sees).
    local_model = empty
    if isinstance(local_history, dict) and (local_history.get("version_specs") or local_history.get("sha_by_id")):
        local_model = dict(local_history)
    else:
        local_tip = head_sha or local_main
        if local_tip and commit_by_sha:
            local_model = build_project_history_model(
                commit_by_sha,
                local_main or local_tip,
                head_sha or local_tip,
                local_review_tips,
                unpushed,
                declined_shas=declined,
            )

    local_shas = _history_shas(local_model)
    remote_shas = _history_shas(remote_model)
    only_remote_shas = remote_shas - local_shas
    only_local_shas = local_shas - remote_shas
    only_remote_main = remote_main_shas - local_main_shas
    only_local_main = local_main_shas - remote_main_shas
    has_remote_extras = bool(only_remote_shas)
    has_local_extras = bool(only_local_shas)
    aligned = not has_remote_extras and not has_local_extras

    conflict = False
    main_base = ""
    conflict_local_shas: set[str] = set()
    conflict_remote_shas: set[str] = set()
    if local_main and origin and local_main != origin and commit_by_sha:
        main_base = _first_parent_merge_base(commit_by_sha, local_main, origin)
        local_is_anc = local_main in remote_main_shas or main_base == local_main
        origin_is_anc = origin in local_main_shas or main_base == origin
        conflict = not local_is_anc and not origin_is_anc
        if conflict and main_base:
            conflict_local_shas = {
                sha
                for sha in _first_parent_chain(commit_by_sha, local_main)
                if sha != main_base and sha not in remote_main_shas
            }
            conflict_remote_shas = {
                sha
                for sha in _first_parent_chain(commit_by_sha, origin)
                if sha != main_base and sha not in local_main_shas
            }
        elif conflict:
            conflict_local_shas = set(only_local_main)
            conflict_remote_shas = set(only_remote_main)

    # Result preview: pedagogical union (merge coming — not applied).
    result_model = empty
    if commit_by_sha:
        merged_tips = dict(remote_review_tips)
        for login, tips in local_review_tips.items():
            bucket = merged_tips.setdefault(login, [])
            for tip in tips:
                if tip not in bucket:
                    bucket.append(tip)
        result_model = build_project_history_model(
            commit_by_sha,
            origin or local_main or head_sha,
            head_sha or origin or local_main,
            merged_tips,
            unpushed,
            declined_shas=declined,
        )

    linear_model = _build_linear_integrate_preview(
        commit_by_sha,
        origin or "",
        local_main or "",
        remote_model,
        only_local_main,
    )

    def _ids_for_shas(model: dict[str, Any], shas: set[str]) -> set[str]:
        sha_by_id = model.get("sha_by_id") or {}
        return {vid for vid, sha in sha_by_id.items() if sha in shas}

    return {
        "local": local_model,
        "remote": remote_model,
        "result": result_model,
        "linear": linear_model,
        "only_local_shas": only_local_shas,
        "only_remote_shas": only_remote_shas,
        "only_local_ids_local": _ids_for_shas(local_model, only_local_shas),
        "only_remote_ids_remote": _ids_for_shas(remote_model, only_remote_shas),
        "only_local_ids_result": _ids_for_shas(result_model, only_local_shas),
        "only_remote_ids_result": _ids_for_shas(result_model, only_remote_shas),
        "conflict_ids_local": _ids_for_shas(local_model, conflict_local_shas),
        "conflict_ids_remote": _ids_for_shas(remote_model, conflict_remote_shas),
        "has_local_extras": has_local_extras,
        "has_remote_extras": has_remote_extras,
        "has_local_main_extras": bool(only_local_main),
        "has_remote_main_extras": bool(only_remote_main),
        "conflict": conflict,
        "aligned": aligned,
        "origin_sha": origin or "",
        "head_sha": head_sha or "",
        "local_main_sha": local_main or "",
        "main_merge_base": main_base or "",
    }


def _build_linear_integrate_preview(
    commit_by_sha: dict[str, dict[str, Any]],
    origin: str,
    local_main: str,
    remote_model: dict[str, Any],
    only_local_main: set[str],
) -> dict[str, Any]:
    """Pedagogical preview: shared main first, then local-only main commits on top."""
    if not remote_model or not (remote_model.get("version_specs") or remote_model.get("sha_by_id")):
        return dict(remote_model or _empty_history_model())
    if not origin or not only_local_main:
        return dict(remote_model)

    remote_main_set = set(_first_parent_chain(commit_by_sha, origin))
    local_only: list[str] = []
    if local_main:
        for sha in reversed(_first_parent_chain(commit_by_sha, local_main)):
            if sha in only_local_main and sha not in remote_main_set:
                local_only.append(sha)
    if not local_only:
        return dict(remote_model)

    sha_by_id = dict(remote_model.get("sha_by_id") or {})
    id_by_sha = {sha: vid for vid, sha in sha_by_id.items()}
    specs_by_id = {spec["id"]: dict(spec) for spec in (remote_model.get("version_specs") or [])}
    tags = dict(remote_model.get("tags_by_id") or {})
    history_rows = [list(row) for row in (remote_model.get("commit_history") or [])]
    existing_ids = {row[0] for row in history_rows if row}

    parent_id = id_by_sha.get(origin)
    main_count = sum(1 for vid in specs_by_id if str(vid).startswith("main/"))
    tip_sha = origin
    for sha in local_only:
        if sha in id_by_sha:
            parent_id = id_by_sha[sha]
            tip_sha = sha
            continue
        main_count += 1
        version_id = "main/%d" % main_count
        specs_by_id[version_id] = {
            "id": version_id,
            "parent": parent_id,
            "branch": "main",
            "tag": version_id,
            "merge": False,
        }
        id_by_sha[sha] = version_id
        sha_by_id[version_id] = sha
        tags[version_id] = version_id
        if version_id not in existing_ids:
            record = commit_by_sha.get(sha) or {}
            history_rows.append(
                [
                    version_id,
                    _format_git_date(str(record.get("date") or "")),
                    str(record.get("author") or ""),
                    str(record.get("message") or ""),
                    "local",
                ]
            )
            existing_ids.add(version_id)
        parent_id = version_id
        tip_sha = sha

    specs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for spec in remote_model.get("version_specs") or []:
        version_id = spec.get("id")
        if version_id and version_id not in seen and version_id in specs_by_id:
            specs.append(specs_by_id[version_id])
            seen.add(version_id)
    for sha in local_only:
        version_id = id_by_sha.get(sha)
        if version_id and version_id not in seen:
            specs.append(specs_by_id[version_id])
            seen.add(version_id)

    return {
        "commit_history": history_rows,
        "version_specs": specs,
        "tags_by_id": tags,
        "sha_by_id": sha_by_id,
        "head_id": id_by_sha.get(tip_sha),
    }


def adopt_shared_main(repo_dir: str) -> None:
    """Point local main (and worktree) at origin/main. Prefer calling after fetch."""
    if not repo_dir or not os.path.isdir(os.path.join(repo_dir, ".git")):
        raise GitHubAuthError("Open the project first.")
    origin = _git_rev_parse(repo_dir, "origin/main")
    if not origin:
        raise GitHubAuthError("Could not find the shared project tip.")
    login = current_login()
    if login:
        _configure_repo_identity(repo_dir, login)
    _run_git(["update-ref", "refs/heads/main", origin], cwd=repo_dir, timeout=20)
    checkout_local_version(repo_dir, origin, "main")
    _run_git(["branch", "--set-upstream-to=origin/main", "main"], cwd=repo_dir, timeout=20)
    _run_git(["update-ref", "refs/remotes/origin/main", origin], cwd=repo_dir, timeout=20)


def _local_only_main_commits(repo_dir: str, origin: str, local_main: str) -> list[str]:
    """Oldest-first first-parent commits on local main that are not on origin/main."""
    if not origin or not local_main:
        return []
    result = _run_git(
        ["rev-list", "--reverse", "--first-parent", "%s..%s" % (origin, local_main)],
        cwd=repo_dir,
        timeout=60,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]


def _replay_snapshot_on_head(repo_dir: str, source_sha: str) -> str:
    """Create a new commit on HEAD with the full tree of source_sha (no 3-way merge).

    Matches Collaborative Versioning snapshots: each local version is replayed as-is
    on top of shared, avoiding binary/rebase conflicts.
    """
    tree = _run_git(
        ["rev-parse", "%s^{tree}" % source_sha], cwd=repo_dir, timeout=30
    )
    if tree.returncode != 0:
        detail = (tree.stderr or tree.stdout or "").strip()
        raise GitHubAuthError(
            "Could not add shared versions then yours.\n%s" % detail[:400]
        )
    tree_sha = (tree.stdout or "").strip()
    head = _git_rev_parse(repo_dir, "HEAD")
    if not tree_sha or not head:
        raise GitHubAuthError("Could not add shared versions then yours.")
    meta = _run_git(
        ["log", "-1", "--format=%an%n%ae%n%aI%n%B", source_sha],
        cwd=repo_dir,
        timeout=30,
    )
    if meta.returncode != 0:
        detail = (meta.stderr or meta.stdout or "").strip()
        raise GitHubAuthError(
            "Could not add shared versions then yours.\n%s" % detail[:400]
        )
    lines = (meta.stdout or "").splitlines()
    author = (lines[0] if len(lines) > 0 else "").strip() or "Collaborative Versioning"
    email = (lines[1] if len(lines) > 1 else "").strip() or "collaborative@versioning.local"
    date = (lines[2] if len(lines) > 2 else "").strip()
    message = "\n".join(lines[3:]).strip() or "Saved version"
    if not message.endswith("\n"):
        message += "\n"
    env_extra = {
        "GIT_AUTHOR_NAME": author,
        "GIT_AUTHOR_EMAIL": email,
    }
    if date:
        env_extra["GIT_AUTHOR_DATE"] = date
    created = _run_git(
        ["commit-tree", tree_sha, "-p", head],
        cwd=repo_dir,
        timeout=60,
        stdin_text=message,
        env_extra=env_extra,
    )
    if created.returncode != 0:
        detail = (created.stderr or created.stdout or "").strip()
        raise GitHubAuthError(
            "Could not add shared versions then yours.\n%s" % detail[:400]
        )
    new_sha = (created.stdout or "").strip()
    if not new_sha:
        raise GitHubAuthError("Could not add shared versions then yours.")
    reset = _run_git(["reset", "--hard", new_sha], cwd=repo_dir, timeout=180)
    if reset.returncode != 0:
        detail = (reset.stderr or reset.stdout or "").strip()
        raise GitHubAuthError(
            "Could not add shared versions then yours.\n%s" % detail[:400]
        )
    return new_sha


def integrate_shared_linear(repo_dir: str) -> None:
    """Put origin/main first, then replay local-only main snapshots on top."""
    if not repo_dir or not os.path.isdir(os.path.join(repo_dir, ".git")):
        raise GitHubAuthError("Open the project first.")
    origin = _git_rev_parse(repo_dir, "origin/main")
    local_main = _git_rev_parse(repo_dir, "refs/heads/main")
    if not origin:
        raise GitHubAuthError("Could not find the shared project tip.")
    if not local_main:
        raise GitHubAuthError("Could not find this computer's main tip.")
    login = current_login()
    if login:
        _configure_repo_identity(repo_dir, login)
    local_only = _local_only_main_commits(repo_dir, origin, local_main)
    if not local_only:
        # Already aligned or only shared is ahead — match shared tip.
        adopt_shared_main(repo_dir)
        return
    # Start from shared tip, then replay each local snapshot in order.
    checkout_local_version(repo_dir, origin, "main")
    tip = origin
    for sha in local_only:
        tip = _replay_snapshot_on_head(repo_dir, sha)
    checkout_local_version(repo_dir, tip, "main")
    _run_git(["branch", "--set-upstream-to=origin/main", "main"], cwd=repo_dir, timeout=20)


def delete_owned_repository(full_name: str) -> None:
    """Delete a GitHub repository the signed-in user owns, and the local clone."""
    ensure_tools()
    login = current_login()
    if not login:
        raise GitHubNotSignedInError(not_signed_in_message())
    owner, _, repo = full_name.partition("/")
    if owner != login or not repo:
        raise GitHubAuthError("Only the owner can delete this project.")
    result = _run_gh(["repo", "delete", full_name, "--yes"], timeout=60)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        if _is_missing_delete_scope(detail):
            raise GitHubMissingDeletePermissionError(
                "GitHub needs an extra permission to delete a project."
            )
        raise GitHubAuthError("Could not delete the project.\n%s" % detail[:400])
    remove_local_project_dir(local_project_dir(full_name))


def _split_project_name(full_name: str) -> tuple[str, str]:
    owner, _, repo = (full_name or "").partition("/")
    if not owner or not repo:
        raise GitHubAuthError("Invalid project name: %s" % full_name)
    return owner, repo


def _load_gh_json(result: subprocess.CompletedProcess, fail_message: str):
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise GitHubAuthError("%s\n%s" % (fail_message, detail[:400]) if detail else fail_message)
    raw = (result.stdout or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise GitHubAuthError(fail_message) from error


def normalize_github_username(username: str) -> str:
    return (username or "").strip().lstrip("@")


def github_username_search_args(prefix: str) -> list[str] | None:
    query = normalize_github_username(prefix)
    if len(query) < 2 or not re.match(r"^[A-Za-z0-9-]{2,39}$", query):
        return None
    return ["api", "search/users?q=%s+in:login&per_page=8" % query]


def parse_github_username_search(raw: str, prefix: str) -> list[str]:
    query = normalize_github_username(prefix)
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, dict):
        return []
    items = payload.get("items")
    if not isinstance(items, list):
        return []
    names = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        login = str(item.get("login") or "").strip()
        key = login.lower()
        if not login or key in seen:
            continue
        seen.add(key)
        names.append(login)
    names.sort(key=lambda login: (not login.lower().startswith(query.lower()), login.lower()))
    return names


def suggest_github_usernames(prefix: str) -> list[str]:
    """GitHub usernames that match what the owner is typing. Empty on failure."""
    args = github_username_search_args(prefix)
    if not args:
        return []
    try:
        result = _run_gh_blocking(args, timeout=8)
        if result.returncode != 0:
            return []
        return parse_github_username_search(result.stdout or "", prefix)
    except (GitHubAuthError, OSError, ValueError, subprocess.TimeoutExpired):
        return []


PEOPLE_ACCESS_SENIOR = "senior"
PEOPLE_ACCESS_JUNIOR = "junior"
_PEOPLE_RIGHTS_PATH = ".collaborative-versioning/people.json"
_MESSAGES_PATH = ".collaborative-versioning/messages.json"
_PROJECT_INFO_BRANCH = "project-info"
_MESSAGE_MAX_LEN = 2000
_TASK_TITLE_MAX_LEN = 200
_ACTIVITY_MAX = 100
_ACTIVITY_READ_IDS_MAX = 200
_ACTIVITY_KINDS = frozenset(
    (
        "join",
        "assign",
        "cancel",
        "submit",
        "accept",
        "decline",
        "share",
        "people_add",
        "people_remove",
    )
)


def normalize_people_access(value: str | None) -> str:
    text = str(value or "").strip().lower().replace("_", "-").replace(" ", "-")
    if text in ("senior", "co-owner", "coowner", "admin"):
        return PEOPLE_ACCESS_SENIOR
    return PEOPLE_ACCESS_JUNIOR


def normalize_task_title(value: str | None) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > _TASK_TITLE_MAX_LEN:
        text = text[:_TASK_TITLE_MAX_LEN].rstrip()
    return text


def _normalize_people_record(login: str, value) -> dict[str, str]:
    name = normalize_github_username(login)
    if isinstance(value, dict):
        access = value.get("access") or value.get("right") or ""
    else:
        access = value
    return {
        "login": name,
        "access": normalize_people_access(str(access) if access is not None else ""),
    }


def _decode_github_file_content(payload) -> str:
    if not isinstance(payload, dict):
        return ""
    raw = str(payload.get("content") or "").replace("\n", "")
    if not raw:
        return ""
    try:
        return base64.b64decode(raw).decode("utf-8")
    except (ValueError, TypeError, UnicodeDecodeError):
        return ""


def _github_contents_payload(owner: str, repo: str, path: str, branch: str):
    result = _run_gh(
        ["api", "repos/%s/%s/contents/%s?ref=%s" % (owner, repo, path, branch)],
        timeout=40,
    )
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _people_records_map(full_name: str) -> dict[str, dict[str, str]]:
    owner, repo = _split_project_name(full_name)
    payload = _github_contents_payload(owner, repo, _PEOPLE_RIGHTS_PATH, _PROJECT_INFO_BRANCH)
    if payload is None:
        return {}
    try:
        document = json.loads(_decode_github_file_content(payload) or "{}")
    except json.JSONDecodeError:
        return {}
    colleagues = document.get("colleagues") if isinstance(document, dict) else None
    if not isinstance(colleagues, dict):
        return {}
    records = {}
    for login, value in colleagues.items():
        name = normalize_github_username(str(login))
        if not name:
            continue
        records[name.lower()] = _normalize_people_record(name, value)
    return records


def _people_access_map(full_name: str) -> dict[str, str]:
    return {
        key: normalize_people_access(record.get("access"))
        for key, record in _people_records_map(full_name).items()
    }


def _people_rights_file_sha(owner: str, repo: str) -> str:
    payload = _github_contents_payload(owner, repo, _PEOPLE_RIGHTS_PATH, _PROJECT_INFO_BRANCH)
    if payload is None:
        return ""
    return str(payload.get("sha") or "").strip()


def _ensure_people_rights_branch(owner: str, repo: str) -> None:
    existing = _run_gh(
        ["api", "repos/%s/%s/git/ref/heads/%s" % (owner, repo, _PROJECT_INFO_BRANCH)],
        timeout=30,
    )
    if existing.returncode == 0:
        return
    repo_info = _run_gh(["api", "repos/%s/%s" % (owner, repo)], timeout=30)
    info = _load_gh_json(repo_info, "Could not read this project.")
    default = str((info or {}).get("default_branch") or "main")
    head = _run_gh(
        ["api", "repos/%s/%s/git/ref/heads/%s" % (owner, repo, default)],
        timeout=30,
    )
    head_payload = _load_gh_json(head, "Could not read the project branch.")
    sha = str(((head_payload or {}).get("object") or {}).get("sha") or "")
    if not sha:
        raise GitHubAuthError("Could not record colleague access for this project.")
    created = _run_gh(
        [
            "api",
            "-X",
            "POST",
            "repos/%s/%s/git/refs" % (owner, repo),
            "-f",
            "ref=refs/heads/%s" % _PROJECT_INFO_BRANCH,
            "-f",
            "sha=%s" % sha,
        ],
        timeout=30,
    )
    if created.returncode == 0:
        return
    detail = (created.stderr or created.stdout or "").strip()
    lower = detail.lower()
    if "already exists" in lower or "reference already exists" in lower:
        return
    raise GitHubAuthError("Could not record colleague access.\n%s" % detail[:400])


def ensure_project_info_branch(full_name: str) -> None:
    """Create the hidden project-info branch once main exists. Safe to call again."""
    owner, repo = _split_project_name(full_name)
    _ensure_people_rights_branch(owner, repo)


def _write_people_records_map(full_name: str, records: dict[str, dict[str, str]]) -> None:
    owner, repo = _split_project_name(full_name)
    colleagues = {}
    for login, record in (records or {}).items():
        stored = record if isinstance(record, dict) else {}
        name = normalize_github_username(str(stored.get("login") or login))
        if not name:
            continue
        entry: dict[str, str] = {"access": normalize_people_access(stored.get("access"))}
        colleagues[name] = entry
    document = json.dumps({"colleagues": colleagues}, separators=(",", ":"), sort_keys=True)
    encoded = base64.b64encode(document.encode("utf-8")).decode("ascii")
    args = [
        "api",
        "--method",
        "PUT",
        "repos/%s/%s/contents/%s" % (owner, repo, _PEOPLE_RIGHTS_PATH),
        "-f",
        "message=Record colleague access",
        "-f",
        "content=%s" % encoded,
        "-f",
        "branch=%s" % _PROJECT_INFO_BRANCH,
    ]
    sha = _people_rights_file_sha(owner, repo)
    if sha:
        args.extend(["-f", "sha=%s" % sha])
    result = _run_gh(args, timeout=40)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise GitHubAuthError("Could not record colleague access.\n%s" % detail[:400])


def set_people_access(full_name: str, username: str, access: str, task: str | None = None) -> None:
    name = normalize_github_username(username)
    if not name:
        raise GitHubAuthError("Enter a GitHub username.")
    current = _people_records_map(full_name)
    records = {key: value for key, value in current.items() if key != name.lower()}
    records[name.lower()] = {
        "login": name,
        "access": normalize_people_access(access),
    }
    _write_people_records_map(full_name, records)


def _is_github_missing(result) -> bool:
    detail = "%s\n%s" % (getattr(result, "stderr", "") or "", getattr(result, "stdout", "") or "")
    lower = detail.lower()
    return "404" in lower or "not found" in lower


def _is_contents_conflict(detail: str) -> bool:
    lower = (detail or "").lower()
    return (
        "409" in lower
        or "sha does not match" in lower
        or "sha doesn't match" in lower
        or "is not a blob" in lower
    )


def _normalize_stored_messages(document) -> list[dict[str, str]]:
    raw = document.get("messages") if isinstance(document, dict) else None
    if not isinstance(raw, list):
        return []
    messages = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        author = str(item.get("author") or "Someone").strip() or "Someone"
        stamp = str(item.get("at") or "").strip()
        mid = str(item.get("id") or "").strip()
        if not mid:
            mid = "%s|%s|%s" % (author, stamp, text[:40])
        entry = {"id": mid, "author": author, "text": text, "at": stamp}
        kind = str(item.get("kind") or "").strip()
        if kind:
            entry["kind"] = kind
        messages.append(entry)
    return messages


def _normalize_stored_tasks(document) -> list[dict[str, str]]:
    raw = document.get("tasks") if isinstance(document, dict) else None
    if not isinstance(raw, list):
        return []
    tasks = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        junior = normalize_github_username(str(item.get("junior") or ""))
        senior = normalize_github_username(str(item.get("senior") or ""))
        if not junior or not senior:
            continue
        tid = str(item.get("id") or "").strip() or ("%s-%s" % (junior, senior))
        key = tid.lower()
        if key in seen:
            continue
        seen.add(key)
        status = str(item.get("status") or "").strip().lower()
        if status not in ("accepted", "submitted"):
            status = ""
        entry = {
            "id": tid,
            "junior": junior,
            "senior": senior,
            "description": normalize_task_title(item.get("description") or item.get("task") or ""),
            "status": status,
        }
        submitted = normalize_task_title(item.get("submitted_description") or "")
        if submitted:
            entry["submitted_description"] = submitted
        tasks.append(entry)
    return tasks


def _normalize_stored_activity(document) -> list[dict[str, str]]:
    raw = document.get("activity") if isinstance(document, dict) else None
    if not isinstance(raw, list):
        return []
    activity = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip().lower()
        if kind not in _ACTIVITY_KINDS:
            continue
        text = " ".join(str(item.get("text") or "").split())
        if not text:
            continue
        if len(text) > _MESSAGE_MAX_LEN:
            text = text[:_MESSAGE_MAX_LEN]
        author = normalize_github_username(str(item.get("author") or "")) or str(
            item.get("author") or "Someone"
        ).strip() or "Someone"
        stamp = str(item.get("at") or "").strip()
        aid = str(item.get("id") or "").strip()
        if not aid:
            aid = "%s|%s|%s|%s" % (kind, author, stamp, text[:40])
        key = aid.lower()
        if key in seen:
            continue
        seen.add(key)
        activity.append(
            {
                "id": aid,
                "kind": kind,
                "author": author,
                "text": text,
                "at": stamp,
            }
        )
    if len(activity) > _ACTIVITY_MAX:
        activity = activity[-_ACTIVITY_MAX:]
    return activity


def project_messages_fetch_args(full_name: str) -> list[str]:
    owner, repo = _split_project_name(full_name)
    return [
        "api",
        "repos/%s/%s/contents/%s?ref=%s" % (owner, repo, _MESSAGES_PATH, _PROJECT_INFO_BRANCH),
    ]


def _normalize_activity_read_ids(raw) -> list[str]:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    ids = []
    seen = set()
    for item in raw:
        aid = str(item or "").strip()
        if not aid or aid in seen:
            continue
        seen.add(aid)
        ids.append(aid)
    if len(ids) > _ACTIVITY_READ_IDS_MAX:
        ids = ids[-_ACTIVITY_READ_IDS_MAX:]
    return ids


def _normalize_stored_reads(document) -> dict[str, dict]:
    raw = document.get("reads") if isinstance(document, dict) else None
    if not isinstance(raw, dict):
        return {}
    reads: dict[str, dict] = {}
    for key, value in raw.items():
        login = normalize_github_username(str(key or ""))
        if not login or not isinstance(value, dict):
            continue
        entry: dict = {}
        for field in ("activity_at", "messages_at", "versions_at"):
            stamp = str(value.get(field) or "").strip()
            if stamp:
                entry[field] = stamp
        ids = _normalize_activity_read_ids(value.get("activity_ids"))
        if ids:
            entry["activity_ids"] = ids
        if entry:
            reads[login.lower()] = entry
    return reads


def parse_project_messages_output(
    stdout: str, stderr: str = "", returncode: int = 0
) -> tuple[
    list[dict[str, str]],
    str,
    list[dict[str, str]],
    list[dict[str, str]],
    dict[str, dict[str, str]],
]:
    class _Result:
        pass

    result = _Result()
    result.stdout = stdout or ""
    result.stderr = stderr or ""
    result.returncode = returncode
    if returncode != 0:
        if _is_github_missing(result):
            return [], "", [], [], {}
        detail = (stderr or stdout or "").strip()
        raise GitHubAuthError("Could not read messages.\n%s" % detail[:400])
    try:
        payload = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        return [], "", [], [], {}
    if not isinstance(payload, dict):
        return [], "", [], [], {}
    try:
        document = json.loads(_decode_github_file_content(payload) or "{}")
    except json.JSONDecodeError:
        document = {}
    return (
        _normalize_stored_messages(document),
        str(payload.get("sha") or "").strip(),
        _normalize_stored_tasks(document),
        _normalize_stored_activity(document),
        _normalize_stored_reads(document),
    )


def build_project_message(author: str, text: str, kind: str = "") -> dict[str, str]:
    body = str(text or "").strip()
    if not body:
        raise GitHubAuthError("Write a message first.")
    if len(body) > _MESSAGE_MAX_LEN:
        body = body[:_MESSAGE_MAX_LEN]
    name = normalize_github_username(author) or str(author or "").strip() or "Someone"
    payload = {
        "id": "%s-%s-%s" % (int(time.time() * 1000), name, os.urandom(3).hex()),
        "author": name,
        "text": body,
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    marker = str(kind or "").strip()
    if marker:
        payload["kind"] = marker
    return payload


def build_project_activity(author: str, kind: str, text: str) -> dict[str, str]:
    marker = str(kind or "").strip().lower()
    if marker not in _ACTIVITY_KINDS:
        raise GitHubAuthError("Unknown activity.")
    body = " ".join(str(text or "").split())
    if not body:
        raise GitHubAuthError("Missing activity text.")
    if len(body) > _MESSAGE_MAX_LEN:
        body = body[:_MESSAGE_MAX_LEN]
    name = normalize_github_username(author) or str(author or "").strip() or "Someone"
    return {
        "id": "%s-%s-%s" % (int(time.time() * 1000), name, os.urandom(3).hex()),
        "kind": marker,
        "author": name,
        "text": body,
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def project_messages_put_args(
    full_name: str,
    messages: list,
    sha: str = "",
    tasks: list | None = None,
    activity: list | None = None,
    reads: dict | None = None,
) -> list[str]:
    owner, repo = _split_project_name(full_name)
    stored = []
    for item in messages or []:
        if not isinstance(item, dict):
            continue
        entry = {
            "id": str(item.get("id") or ""),
            "author": str(item.get("author") or "Someone"),
            "text": str(item.get("text") or ""),
            "at": str(item.get("at") or ""),
        }
        kind = str(item.get("kind") or "").strip()
        if kind:
            entry["kind"] = kind
        stored.append(entry)
    document = json.dumps(
        {
            "messages": stored,
            "tasks": _normalize_stored_tasks({"tasks": list(tasks or [])}),
            "activity": _normalize_stored_activity({"activity": list(activity or [])}),
            "reads": _normalize_stored_reads({"reads": dict(reads or {})}),
        },
        separators=(",", ":"),
    )
    encoded = base64.b64encode(document.encode("utf-8")).decode("ascii")
    args = [
        "api",
        "--method",
        "PUT",
        "repos/%s/%s/contents/%s" % (owner, repo, _MESSAGES_PATH),
        "-f",
        "message=Add project message",
        "-f",
        "content=%s" % encoded,
        "-f",
        "branch=%s" % _PROJECT_INFO_BRANCH,
    ]
    if sha:
        args.extend(["-f", "sha=%s" % sha])
    return args


def is_project_messages_conflict(stdout: str = "", stderr: str = "") -> bool:
    return _is_contents_conflict("%s\n%s" % (stderr or "", stdout or ""))


def publish_project_activity(
    full_name: str,
    kind: str = "",
    text: str = "",
    event: dict | None = None,
) -> None:
    """Append one project activity event. Safe to call after Share / People / Join.

    Pass a pre-built event to keep its timestamp (e.g. built at Share time, published
    after a UI popup so the network wait does not delay the dialog).
    """
    if not full_name:
        return
    try:
        ensure_project_info_branch(full_name)
    except (GitHubAuthError, OSError, ValueError):
        pass
    if event is None:
        event = build_project_activity(current_login() or "Someone", kind, text)
    elif not isinstance(event, dict) or not str(event.get("id") or "").strip():
        return
    last_error = ""
    for _attempt in range(4):
        fetch = _run_gh(project_messages_fetch_args(full_name), timeout=40)
        try:
            messages, sha, tasks, activity, reads = parse_project_messages_output(
                fetch.stdout or "",
                fetch.stderr or "",
                fetch.returncode,
            )
        except GitHubAuthError as error:
            last_error = str(error)
            break
        merged = list(activity or [])
        if not any(str(item.get("id") or "") == event["id"] for item in merged):
            merged.append(event)
        put = _run_gh(
            project_messages_put_args(
                full_name,
                messages,
                sha=sha,
                tasks=tasks,
                activity=merged,
                reads=reads,
            ),
            timeout=40,
        )
        if put.returncode == 0:
            return
        detail = "%s\n%s" % (put.stderr or "", put.stdout or "")
        if is_project_messages_conflict(put.stdout or "", put.stderr or ""):
            continue
        last_error = detail.strip()
        break
    if last_error:
        raise GitHubAuthError("Could not record the notification.\n%s" % last_error[:400])


def forget_people_access(full_name: str, username: str) -> None:
    name = normalize_github_username(username)
    if not name:
        return
    try:
        records = _people_records_map(full_name)
        cleaned = {key: value for key, value in records.items() if key != name.lower()}
        if cleaned == records:
            return
        _write_people_records_map(full_name, cleaned)
    except (GitHubAuthError, OSError, ValueError):
        return


def _person_access_fields(records: dict[str, dict[str, str]], login: str) -> dict[str, str]:
    record = records.get(login.lower()) or {}
    return {"access": normalize_people_access(record.get("access"))}


def list_project_people(full_name: str) -> list[dict[str, str]]:
    """Owner, colleagues, and pending invitations for a project."""
    owner, repo = _split_project_name(full_name)
    records = _people_records_map(full_name)
    people: list[dict[str, str]] = [{"login": owner, "role": "owner"}]
    seen = {owner.lower()}
    collab = _run_gh(
        ["api", "repos/%s/%s/collaborators?per_page=100" % (owner, repo)],
        timeout=60,
    )
    payload = _load_gh_json(collab, "Could not read who is on this project.")
    if isinstance(payload, list):
        colleagues = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            login = str(item.get("login") or "").strip()
            if not login or login.lower() in seen:
                continue
            seen.add(login.lower())
            person = {"login": login, "role": "colleague"}
            person.update(_person_access_fields(records, login))
            colleagues.append(person)
        colleagues.sort(key=lambda item: item["login"].lower())
        people.extend(colleagues)
    invites = _run_gh(
        ["api", "repos/%s/%s/invitations?per_page=100" % (owner, repo)],
        timeout=60,
    )
    if invites.returncode != 0:
        detail = (invites.stderr or invites.stdout or "").strip().lower()
        if (
            "403" in detail
            or "404" in detail
            or "not found" in detail
            or "resource not accessible" in detail
        ):
            return people
        raise GitHubAuthError("Could not read pending invitations.\n%s" % (invites.stderr or invites.stdout or "")[:400])
    invite_payload = _load_gh_json(invites, "Could not read pending invitations.")
    if isinstance(invite_payload, list):
        pending = []
        for item in invite_payload:
            if not isinstance(item, dict):
                continue
            invitee = item.get("invitee") if isinstance(item.get("invitee"), dict) else {}
            login = str((invitee or {}).get("login") or item.get("email") or "").strip()
            if not login or login.lower() in seen:
                continue
            seen.add(login.lower())
            person = {
                "login": login,
                "role": "pending",
                "invitation_id": item.get("id"),
            }
            person.update(_person_access_fields(records, login))
            pending.append(person)
        pending.sort(key=lambda item: item["login"].lower())
        people.extend(pending)
    return people


def invite_project_colleague(
    full_name: str,
    username: str,
    access: str = PEOPLE_ACCESS_JUNIOR,
    task: str = "",
) -> str:
    """Invite a GitHub user as senior or junior. Returns invited or already."""
    owner, repo = _split_project_name(full_name)
    name = normalize_github_username(username)
    chosen = normalize_people_access(access)
    if not name:
        raise GitHubAuthError("Enter a GitHub username.")
    if not re.match(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$", name):
        raise GitHubAuthError("That GitHub username is not valid.")
    if name.lower() == owner.lower():
        raise GitHubAuthError("You are already the owner of this project.")
    result = _run_gh(
        [
            "api",
            "-X",
            "PUT",
            "repos/%s/%s/collaborators/%s" % (owner, repo, name),
            "-f",
            "permission=push",
        ],
        timeout=40,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        lower = detail.lower()
        if "not found" in lower or "404" in lower:
            raise GitHubAuthError("GitHub user not found: %s." % name)
        raise GitHubAuthError("Could not send the invitation.\n%s" % detail[:400])
    set_people_access(full_name, name, chosen)
    if not (result.stdout or "").strip():
        return "already"
    return "invited"


def remove_project_colleague(full_name: str, username: str) -> None:
    """Remove a colleague's access to the project."""
    owner, repo = _split_project_name(full_name)
    name = normalize_github_username(username)
    if not name:
        raise GitHubAuthError("Select a colleague first.")
    if name.lower() == owner.lower():
        raise GitHubAuthError("You cannot remove the owner.")
    result = _run_gh_blocking(
        [
            "api",
            "--hostname",
            "github.com",
            "--method",
            "DELETE",
            "--input",
            "NUL" if os.name == "nt" else "/dev/null",
            "repos/%s/%s/collaborators/%s" % (owner, repo, name),
        ],
        timeout=20,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise GitHubAuthError("Could not remove %s.\n%s" % (name, detail[:400]))


def cancel_project_invitation(full_name: str, invitation_id) -> None:
    """Cancel a pending invitation without opening a web browser."""
    owner, repo = _split_project_name(full_name)
    if invitation_id is None:
        raise GitHubAuthError("Could not cancel the invitation.")
    result = _run_gh_blocking(
        [
            "api",
            "--hostname",
            "github.com",
            "--method",
            "DELETE",
            "--input",
            "NUL" if os.name == "nt" else "/dev/null",
            "repos/%s/%s/invitations/%s" % (owner, repo, invitation_id),
        ],
        timeout=20,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise GitHubAuthError("Could not cancel the invitation.\n%s" % detail[:400])


def incoming_invitations_fetch_args() -> list[str]:
    return ["api", "user/repository_invitations?per_page=20"]


def parse_incoming_invitations_output(
    stdout: str, stderr: str = "", returncode: int = 0
) -> list[dict[str, Any]]:
    if returncode != 0:
        detail = (stderr or stdout or "").strip()
        raise GitHubAuthError("Could not check invitations.\n%s" % detail[:400])
    try:
        payload = json.loads(stdout or "[]")
    except json.JSONDecodeError:
        return []
    invitations = []
    if not isinstance(payload, list):
        return invitations
    for item in payload:
        if not isinstance(item, dict):
            continue
        invitation_id = item.get("id")
        repository = item.get("repository") if isinstance(item.get("repository"), dict) else {}
        full_name = str((repository or {}).get("full_name") or "").strip()
        inviter = item.get("inviter") if isinstance(item.get("inviter"), dict) else {}
        if invitation_id is None or not full_name:
            continue
        invitations.append(
            {
                "id": invitation_id,
                "full_name": full_name,
                "inviter": str((inviter or {}).get("login") or "").strip(),
                "kind": "invite",
            }
        )
    invitations.sort(key=lambda item: item["full_name"].lower())
    return invitations


def accept_project_invitation(invitation_id) -> None:
    """Accept a project invitation without opening a web browser."""
    ensure_tools()
    result = _run_gh(
        ["api", "-X", "PATCH", "user/repository_invitations/%s" % invitation_id],
        timeout=40,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise GitHubAuthError("Could not join the project.\n%s" % detail[:400])


def decline_project_invitation(invitation_id) -> None:
    """Decline a project invitation without opening a web browser."""
    ensure_tools()
    result = _run_gh(
        ["api", "-X", "DELETE", "user/repository_invitations/%s" % invitation_id],
        timeout=40,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise GitHubAuthError("Could not decline the invitation.\n%s" % detail[:400])
