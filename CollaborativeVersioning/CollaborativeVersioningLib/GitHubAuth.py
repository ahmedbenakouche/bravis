"""Talk to GitHub through the Git and GitHub CLI (gh) already on the machine."""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
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
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["GH_PAGER"] = ""
    env["GIT_PAGER"] = ""
    env["GH_PROMPT_DISABLED"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
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


def _run_git(args: list[str], cwd: str, timeout: int = 120) -> subprocess.CompletedProcess:
    git = find_git()
    if not git:
        raise GitHubAuthError(missing_tools_message())
    return _run_captured([git, *args], timeout, cwd, "Git")


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


def _git_show_to_file(repo_dir: str, sha: str, git_path: str, dest_file: str, timeout: int = 120) -> None:
    git = find_git()
    if not git:
        raise GitHubAuthError(missing_tools_message())
    parent = os.path.dirname(dest_file)
    if parent:
        os.makedirs(parent, exist_ok=True)
    env = os.environ.copy()
    env["GIT_PAGER"] = ""
    env["GIT_TERMINAL_PROMPT"] = "0"
    stderr_chunks: list[bytes] = []

    def _drain_err(stream) -> None:
        try:
            stderr_chunks.append(stream.read() or b"")
        except Exception:
            pass

    with open(dest_file, "wb") as outgoing:
        try:
            process = subprocess.Popen(
                [git, "show", "%s:%s" % (sha, git_path)],
                cwd=repo_dir,
                stdin=subprocess.DEVNULL,
                stdout=outgoing,
                stderr=subprocess.PIPE,
                env=env,
                **_windows_create_no_window(),
            )
        except OSError as error:
            raise GitHubAuthError("Could not run Git: %s" % error) from error
        reader = threading.Thread(target=_drain_err, args=(process.stderr,))
        reader.daemon = True
        reader.start()
        start = time.time()
        while True:
            if timeout - (time.time() - start) <= 0:
                process.kill()
                reader.join(timeout=1)
                raise GitHubAuthError("Git timed out.")
            if process.poll() is not None:
                reader.join(timeout=2)
                if process.returncode != 0:
                    detail = b"".join(stderr_chunks).decode("utf-8", "replace").strip()
                    raise GitHubAuthError("Could not switch version.\n%s" % detail[:400])
                return
            _pump_wait()
            time.sleep(0.05)


def extract_project_version(repo_dir: str, sha: str) -> str:
    """Write this version's segmentation and ontology into a temp folder. Volume is skipped."""
    if not repo_dir or not os.path.isdir(os.path.join(repo_dir, ".git")):
        raise GitHubAuthError("Open the project first.")
    if not sha:
        raise GitHubAuthError("Could not switch version.")
    paths = [path for path in _list_commit_paths(repo_dir, sha) if not _commit_path_is_volume(path)]
    if not paths:
        raise GitHubAuthError("Could not switch version.")
    dest = tempfile.mkdtemp(prefix="CollaborativeVersioning-")
    try:
        for path in paths:
            outgoing = os.path.join(dest, *path.split("/"))
            _git_show_to_file(repo_dir, sha, path, outgoing)
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    return dest


def commit_local_version(repo_dir: str, message: str) -> None:
    """Commit all files in the local project folder. Does not publish them."""
    _stage_and_commit(repo_dir, message, "Could not save the version.")


def _share_failure_message(detail: str) -> str:
    lower = (detail or "").lower()
    if (
        "non-fast-forward" in lower
        or "failed to push some refs" in lower
        or "updates were rejected" in lower
    ):
        return (
            "Could not share. The shared project has versions that are not on this computer.\n\n"
            "Open the project and choose Open shared project first, then share again."
        )
    if "permission" in lower or "403" in lower or "write access" in lower:
        return "Could not share. This project is read-only for your account."
    return "Could not share the project yet.\n%s" % (detail or "")[:400]


def share_local_versions(repo_dir: str) -> None:
    """Publish saved local versions. Does not create a new version."""
    if not repo_dir or not os.path.isdir(os.path.join(repo_dir, ".git")):
        raise GitHubAuthError("Open the project first.")
    origin = _run_git(["rev-parse", "--verify", "--quiet", "origin/main"], cwd=repo_dir, timeout=30)
    if origin.returncode == 0 and not _unpushed_commit_shas(repo_dir):
        raise GitHubAuthError("No new versions to share.")
    login = current_login()
    if login:
        _configure_repo_identity(repo_dir, login)
    _run_git(["branch", "-M", "main"], cwd=repo_dir)
    push = _run_git(["push", "-u", "origin", "main"], cwd=repo_dir, timeout=180)
    if push.returncode != 0:
        raise GitHubAuthError(_share_failure_message((push.stderr or push.stdout or "").strip()))


def people_access_for(full_name: str, login: str | None = None) -> str:
    """share = publish now; approval = owner must accept. Owner always share."""
    owner, _repo = _split_project_name(full_name)
    name = normalize_github_username(login or current_login() or "")
    if not name or name.lower() == owner.lower():
        return PEOPLE_ACCESS_SHARE
    return _people_access_map(full_name).get(name.lower()) or PEOPLE_ACCESS_SHARE


def review_branch_for(login: str) -> str:
    name = normalize_github_username(login) or "colleague"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-") or "colleague"
    return "cv-review/%s" % safe


def submit_share_request(repo_dir: str, full_name: str) -> str:
    """Send saved versions for the owner to review. Returns sent or updated."""
    if not repo_dir or not os.path.isdir(os.path.join(repo_dir, ".git")):
        raise GitHubAuthError("Open the project first.")
    origin = _run_git(["rev-parse", "--verify", "--quiet", "origin/main"], cwd=repo_dir, timeout=30)
    if origin.returncode == 0 and not _unpushed_commit_shas(repo_dir):
        raise GitHubAuthError("No new versions to share.")
    login = current_login()
    if not login:
        raise GitHubNotSignedInError(not_signed_in_message())
    _configure_repo_identity(repo_dir, login)
    _run_git(["branch", "-M", "main"], cwd=repo_dir)
    branch = review_branch_for(login)
    push = _run_git(
        ["push", "--force-with-lease", "origin", "HEAD:refs/heads/%s" % branch],
        cwd=repo_dir,
        timeout=180,
    )
    if push.returncode != 0:
        push = _run_git(
            ["push", "origin", "HEAD:refs/heads/%s" % branch],
            cwd=repo_dir,
            timeout=180,
        )
    if push.returncode != 0:
        raise GitHubAuthError(_share_failure_message((push.stderr or push.stdout or "").strip()))
    title = "Share request from %s" % login
    body = "A colleague sent a version for the owner to review in 3D Slicer."
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


def notification_review_fetch_args(owner: str) -> list[str]:
    return ["api", "search/issues?q=is:pr+is:open+user:%s&per_page=20" % owner]


def parse_share_request_search_output(
    stdout: str, stderr: str = "", returncode: int = 0
) -> list[dict[str, Any]]:
    if returncode != 0:
        detail = (stderr or stdout or "").strip()
        raise GitHubAuthError("Could not check notifications.\n%s" % detail[:400])
    try:
        payload = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        return []
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []
    requests = []
    seen = set()
    for item in items:
        parsed = _share_request_from_search_item(item)
        if parsed is None:
            continue
        key = "%s#%s" % (parsed["full_name"], parsed["number"])
        if key in seen:
            continue
        seen.add(key)
        parsed["kind"] = "review"
        requests.append(parsed)
    return requests


def _share_request_from_search_item(item: dict) -> dict[str, Any] | None:
    if not isinstance(item, dict) or not item.get("pull_request"):
        return None
    title = str(item.get("title") or "")
    repo_url = str(item.get("repository_url") or "")
    full_name = repo_url.rsplit("/repos/", 1)[-1].strip("/") if "/repos/" in repo_url else ""
    if not full_name or "/" not in full_name:
        return None
    user = item.get("user") if isinstance(item.get("user"), dict) else {}
    author_login = str((user or {}).get("login") or "").strip()
    branch = ""
    if title.lower().startswith("share request"):
        branch = review_branch_for(author_login)
    if not branch:
        return None
    number = item.get("number")
    if number is None:
        return None
    return {
        "number": number,
        "full_name": full_name,
        "author": author_login,
        "branch": branch,
        "title": title,
    }


def fetch_share_request_sha(full_name: str, branch: str) -> tuple[str, str]:
    """Fetch a review line and return (local clone, commit sha). Does not change main."""
    dest = open_or_update_local_project(full_name, mode="update")
    fetch = _run_git(["fetch", "origin", branch], cwd=dest, timeout=180)
    if fetch.returncode != 0:
        detail = (fetch.stderr or fetch.stdout or "").strip()
        raise GitHubAuthError("Could not open the version to review.\n%s" % detail[:400])
    sha = _run_git(["rev-parse", "origin/%s" % branch], cwd=dest, timeout=30)
    value = (sha.stdout or "").strip()
    if sha.returncode != 0 or not value:
        raise GitHubAuthError("Could not open the version to review.")
    return dest, value


def accept_share_request(full_name: str, branch: str, number) -> str:
    """Fast-forward the project line with the reviewed version."""
    dest, _sha = fetch_share_request_sha(full_name, branch)
    push = _run_git(
        ["push", "origin", "origin/%s:refs/heads/main" % branch],
        cwd=dest,
        timeout=180,
    )
    if push.returncode != 0:
        raise GitHubAuthError(_share_failure_message((push.stderr or push.stdout or "").strip()))
    _run_git(["fetch", "origin", "main"], cwd=dest, timeout=180)
    _run_git(["reset", "--hard", "origin/main"], cwd=dest, timeout=60)
    try:
        _run_gh_blocking(
            [
                "pr",
                "close",
                str(number),
                "--repo",
                full_name,
                "--delete-branch",
            ],
            timeout=15,
        )
    except GitHubAuthError:
        pass
    return dest


def decline_share_request(full_name: str, number) -> None:
    result = _run_gh(
        [
            "pr",
            "close",
            str(number),
            "--repo",
            full_name,
            "--delete-branch",
        ],
        timeout=40,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        lower = detail.lower()
        if "already" in lower or "not found" in lower:
            return
        raise GitHubAuthError("Could not decline the version.\n%s" % detail[:400])


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
        pull = _run_git(["pull"], cwd=dest, timeout=180)
        if pull.returncode != 0:
            detail = (pull.stderr or pull.stdout or "").strip()
            raise GitHubAuthError("Could not update the local project.\n%s" % detail[:400])
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


def read_project_history(repo_dir: str) -> dict[str, Any]:
    """Read saved versions from the local project folder (oldest = main/1)."""
    empty = {"commit_history": [], "version_specs": [], "tags_by_id": {}, "sha_by_id": {}}
    if not repo_dir or not os.path.isdir(os.path.join(repo_dir, ".git")):
        return empty
    result = _run_git(
        ["log", "--reverse", "--format=%H%x1f%cI%x1f%an%x1f%s"],
        cwd=repo_dir,
        timeout=60,
    )
    if result.returncode != 0:
        return empty
    commits = []
    for line in (result.stdout or "").splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f")
        if len(parts) < 4:
            continue
        commits.append((parts[0], parts[1], parts[2], parts[3]))
    unpushed = _unpushed_commit_shas(repo_dir)
    specs = []
    history_newest_first = []
    tags = {}
    sha_by_id = {}
    parent = None
    total = len(commits)
    for index, (sha, iso, author, message) in enumerate(commits, start=1):
        version_id = "main/%d" % index
        tags[version_id] = version_id
        sha_by_id[version_id] = sha
        specs.append(
            {
                "id": version_id,
                "parent": parent,
                "branch": "main",
                "tag": version_id,
                "head": index == total,
            }
        )
        history_newest_first.append(
            [
                version_id,
                _format_git_date(iso),
                author,
                message,
                "local" if sha in unpushed else "pushed",
            ]
        )
        parent = version_id
    history_newest_first.reverse()
    return {
        "commit_history": history_newest_first,
        "version_specs": specs,
        "tags_by_id": tags,
        "sha_by_id": sha_by_id,
    }


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


PEOPLE_ACCESS_SHARE = "share"
PEOPLE_ACCESS_APPROVAL = "approval"
_PEOPLE_RIGHTS_PATH = ".collaborative-versioning/people.json"
_MESSAGES_PATH = ".collaborative-versioning/messages.json"
_PROJECT_INFO_BRANCH = "project-info"
_MESSAGE_MAX_LEN = 2000
_TASK_TITLE_MAX_LEN = 80


def normalize_people_access(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if text in ("approval", "needs approval", "propose", "review"):
        return PEOPLE_ACCESS_APPROVAL
    return PEOPLE_ACCESS_SHARE


def normalize_task_title(value: str | None) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > _TASK_TITLE_MAX_LEN:
        text = text[:_TASK_TITLE_MAX_LEN].rstrip()
    return text


def _normalize_people_record(login: str, value) -> dict[str, str]:
    name = normalize_github_username(login)
    if isinstance(value, dict):
        access = value.get("access") or value.get("right") or ""
        task = value.get("task") or value.get("title") or ""
    else:
        access = value
        task = ""
    return {
        "login": name,
        "access": normalize_people_access(str(access) if access is not None else ""),
        "task": normalize_task_title(task),
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
        key: str(record.get("access") or PEOPLE_ACCESS_SHARE)
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
        task = normalize_task_title(stored.get("task"))
        if task:
            entry["task"] = task
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
    previous = current.get(name.lower()) or {}
    kept_task = previous.get("task") or ""
    if task is not None:
        kept_task = normalize_task_title(task)
    records = {key: value for key, value in current.items() if key != name.lower()}
    records[name.lower()] = {
        "login": name,
        "access": normalize_people_access(access),
        "task": kept_task,
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
        messages.append({"id": mid, "author": author, "text": text, "at": stamp})
    return messages


def project_messages_fetch_args(full_name: str) -> list[str]:
    owner, repo = _split_project_name(full_name)
    return [
        "api",
        "repos/%s/%s/contents/%s?ref=%s" % (owner, repo, _MESSAGES_PATH, _PROJECT_INFO_BRANCH),
    ]


def parse_project_messages_output(
    stdout: str, stderr: str = "", returncode: int = 0
) -> tuple[list[dict[str, str]], str]:
    class _Result:
        pass

    result = _Result()
    result.stdout = stdout or ""
    result.stderr = stderr or ""
    result.returncode = returncode
    if returncode != 0:
        if _is_github_missing(result):
            return [], ""
        detail = (stderr or stdout or "").strip()
        raise GitHubAuthError("Could not read messages.\n%s" % detail[:400])
    try:
        payload = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        return [], ""
    if not isinstance(payload, dict):
        return [], ""
    try:
        document = json.loads(_decode_github_file_content(payload) or "{}")
    except json.JSONDecodeError:
        document = {}
    return _normalize_stored_messages(document), str(payload.get("sha") or "").strip()


def build_project_message(author: str, text: str) -> dict[str, str]:
    body = str(text or "").strip()
    if not body:
        raise GitHubAuthError("Write a message first.")
    if len(body) > _MESSAGE_MAX_LEN:
        body = body[:_MESSAGE_MAX_LEN]
    name = normalize_github_username(author) or str(author or "").strip() or "Someone"
    return {
        "id": "%s-%s-%s" % (int(time.time() * 1000), name, os.urandom(3).hex()),
        "author": name,
        "text": body,
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def project_messages_put_args(full_name: str, messages: list, sha: str = "") -> list[str]:
    owner, repo = _split_project_name(full_name)
    stored = []
    for item in messages or []:
        if not isinstance(item, dict):
            continue
        stored.append(
            {
                "id": str(item.get("id") or ""),
                "author": str(item.get("author") or "Someone"),
                "text": str(item.get("text") or ""),
                "at": str(item.get("at") or ""),
            }
        )
    document = json.dumps({"messages": stored}, separators=(",", ":"))
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


def _person_task_fields(records: dict[str, dict[str, str]], login: str) -> dict[str, str]:
    record = records.get(login.lower()) or {}
    task = normalize_task_title(record.get("task"))
    fields = {"access": record.get("access") or PEOPLE_ACCESS_SHARE}
    if task:
        fields["task"] = task
    return fields


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
            person.update(_person_task_fields(records, login))
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
            person.update(_person_task_fields(records, login))
            pending.append(person)
        pending.sort(key=lambda item: item["login"].lower())
        people.extend(pending)
    return people


def invite_project_colleague(
    full_name: str,
    username: str,
    access: str = PEOPLE_ACCESS_SHARE,
    task: str = "",
) -> str:
    """Invite a GitHub user with write access. Returns invited or already."""
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
    set_people_access(full_name, name, chosen, task=task)
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
