#!/usr/bin/env python3
"""Mirror every Gitea repository into a private GitHub repository.

Gitea lives on a private network. The job runs on the self-hosted runner, which
is on the tailnet and reaches Gitea through the bridge. Each run lists every
repo the Gitea token can see (a site admin's token sees all of them) and, per
repo:

  * creates a private GitHub repo named <gitea-owner>-<name> if there isn't one
    yet, with the `gitea-mirror` topic and a description naming its Gitea
    source. A repo whose description doesn't name that exact source, or a
    public one, is never pushed to, so an existing GitHub repo can't be
    clobbered by a name clash and private code can't land in a public repo;
  * turns GitHub Actions off on it before anything is pushed, so mirrored
    .github/workflows never run. .drone.yml and .gitea/workflows are mirrored
    as-is; GitHub ignores them;
  * compares branch and tag tips, and only when they differ fetches from Gitea
    and force-pushes, deleting branches and tags that are gone upstream.

Gitea is the source of truth: anything pushed to a mirror directly is
overwritten on the next sync. Mirrors of repos deleted from Gitea are left
alone, never deleted.

The runner is shared, so a sync has to stay cheap:
  * each repo is kept in a cache on the runner, so a change upstream fetches
    only the new objects instead of the whole history;
  * a repo that fails is marked with a `mirror-failing-<fingerprint>` topic and
    skipped until something changes in Gitea, rather than being re-uploaded in
    full every 15 minutes. Running the workflow by hand with "retry failed"
    tries them all again.

This runs in a public repo, so the log is public. Repo names never reach it:
each repo is reported by a short hash of its Gitea name, and git's errors are
shown with URLs, refs, paths and emails cut out. To map a hash back:
    python3 -c 'import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:10])' owner/name

Env:
    GITEA_URL       Gitea base URL as reachable from the runner
    GITEA_TOKEN     Gitea access token, scope read:repository
    MIRROR_TOKEN    GitHub token for the account that owns the mirrors
    GITHUB_API_URL, GITHUB_SERVER_URL   set by Actions; default to github.com
    MIRROR_CACHE    where to keep the repo cache; defaults to the runner's
                    tool cache, or a throwaway directory outside Actions
    MIRROR_RETRY_FAILED  "true" to retry repos marked as failing
    MIRROR_VERBOSE  set to print full errors (local runs only: they name repos)
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

TOPIC = "gitea-mirror"
FAILING = "mirror-failing-"
REFSPECS = ["+refs/heads/*:refs/heads/*", "+refs/tags/*:refs/tags/*"]
GIT_TIMEOUT = 60 * 60
# A Gitea pull mirror is a copy of something hosted elsewhere, often GitHub
# itself; mirroring it back would only duplicate it.
SKIP_PULL_MIRRORS = True
RETRY_FAILED = os.environ.get("MIRROR_RETRY_FAILED", "").lower() == "true"
VERBOSE = bool(os.environ.get("MIRROR_VERBOSE"))


class Fail(Exception):
    """A per-repo failure. The message is printed publicly, so no names."""


def rid(full_name: str) -> str:
    return hashlib.sha256(full_name.encode()).hexdigest()[:10]


def detail(msg: str) -> None:
    if VERBOSE:
        print(f"    {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def request(method: str, url: str, headers: dict, body: object = None) -> tuple[int, object]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "User-Agent": "gitea-mirror", **headers,
    })
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        detail(f"{method} {url} -> {exc.code} {exc.read()[:300]!r}")
        return exc.code, None


class Gitea:
    def __init__(self, url: str, token: str) -> None:
        self.url = url.rstrip("/")
        self.headers = {"Accept": "application/json", "Authorization": f"token {token}"}

    def reachable(self) -> bool:
        """Any HTTP answer counts: a bad token should fail as a bad token."""
        try:
            request("GET", f"{self.url}/api/v1/version", self.headers)
        except (urllib.error.URLError, OSError) as exc:
            detail(f"version check: {exc}")
            return False
        return True

    def repos(self) -> list[dict]:
        found: dict[str, dict] = {}
        for page in range(1, 1000):
            status, body = request(
                "GET", f"{self.url}/api/v1/repos/search?limit=50&page={page}&sort=id&order=asc",
                self.headers,
            )
            if status != 200 or not isinstance(body, dict) or not body.get("ok"):
                raise Fail(f"Gitea repo listing failed (HTTP {status}); check GITEA_TOKEN")
            batch = body.get("data") or []
            if not batch:
                break
            for repo in batch:
                found[repo["full_name"]] = repo
        return list(found.values())


class GitHub:
    def __init__(self, api: str, token: str) -> None:
        self.api = api.rstrip("/")
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def call(self, method: str, path: str, body: object = None) -> tuple[int, object]:
        return request(method, self.api + path, self.headers, body)

    def must(self, method: str, path: str, body: object, ok: int, what: str) -> object:
        status, out = self.call(method, path, body)
        if status != ok:
            raise Fail(f"{what} failed (HTTP {status})")
        return out


# ---------------------------------------------------------------------------
# git
# ---------------------------------------------------------------------------

REASONS = [
    ("GH001", "a file is over GitHub's 100 MB limit"),
    ("GH007", "GitHub refused commits carrying an email you keep private; turn off "
              "\"Block command line pushes that expose my email\" at github.com/settings/emails"),
    ("pack exceeds maximum allowed size", "the push is over GitHub's 2 GB limit"),
    ("refusing to allow", "MIRROR_TOKEN can't push workflow files; it needs the Workflows permission"),
    ("Authentication failed", "authentication failed"),
    ("could not read Username", "authentication failed"),
    ("error: 403", "permission denied"),
    ("Permission to", "permission denied"),
    ("Repository not found", "repository not found"),
    ("Could not resolve host", "network error"),
    ("Failed to connect", "network error"),
]


def excerpt(stderr: str) -> str:
    """git's own error lines, with anything that could name a repo, branch,
    file or person cut out, so they're safe for a public log."""
    out: list[str] = []
    for line in stderr.splitlines():
        line = line.strip()
        if not re.match(r"(fatal|error|remote: (fatal|error)|! \[)", line):
            continue
        line = re.sub(r"\] .* -> \S+", "]", line)  # ref update lines
        line = re.sub(r"\S+://\S+|'[^']*'|\"[^\"]*\"|refs/\S+|\S+\.git\b|\S+@\S+", "…", line)
        line = re.sub(r"\b(File|Permission to|path:?|refspec|destination:?) \S+", r"\1 …", line)
        out.append(line)
    return "; ".join(dict.fromkeys(out))[:400]


def git_env(gitea_url: str, gitea_token: str, server: str, gh_token: str) -> dict:
    """Credentials go in as per-host headers through the environment: never
    in a URL, where they would end up in error messages, nor on the command
    line, where other users on the runner could read them."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("GITEA_TOKEN", "MIRROR_TOKEN", "STATS_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")}
    basic = base64.b64encode(f"x-access-token:{gh_token}".encode()).decode()
    config = [
        ("credential.helper", ""),
        (f"http.{gitea_url.rstrip('/')}/.extraHeader", f"Authorization: token {gitea_token}"),
        (f"http.{server.rstrip('/')}/.extraHeader", f"Authorization: Basic {basic}"),
        # Give up on a transfer that has stalled, rather than on one that is
        # merely big: under 1 KB/s for 10 minutes.
        ("http.lowSpeedLimit", "1000"),
        ("http.lowSpeedTime", "600"),
    ]
    env["GIT_CONFIG_COUNT"] = str(len(config))
    for i, (key, value) in enumerate(config):
        env[f"GIT_CONFIG_KEY_{i}"] = key
        env[f"GIT_CONFIG_VALUE_{i}"] = value
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


class Git:
    def __init__(self, env: dict) -> None:
        self.env = env

    def __call__(self, *args: str) -> str:
        sub = args[2] if args[0] == "-C" else args[0]
        try:
            proc = subprocess.run(["git", *args], env=self.env, capture_output=True, check=False,
                                  text=True, timeout=GIT_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise Fail(f"git {sub}: still running after {GIT_TIMEOUT // 60} minutes") from None
        if proc.returncode != 0:
            detail(proc.stderr.strip())
            reason = next((why for needle, why in REASONS if needle in proc.stderr), None)
            raise Fail(f"git {sub}: {reason or excerpt(proc.stderr) or f'exited {proc.returncode}'}")
        return proc.stdout

    def refs(self, url: str) -> dict[str, str]:
        """Branch and tag tips, including peeled tags, as {ref: sha}."""
        out = {}
        for line in self("ls-remote", url).splitlines():
            sha, _, ref = line.partition("\t")
            if ref.startswith(("refs/heads/", "refs/tags/")):
                out[ref] = sha
        return out


# ---------------------------------------------------------------------------
# One repo
# ---------------------------------------------------------------------------


def mirror_name(full_name: str) -> str:
    owner, _, name = full_name.partition("/")
    return f"{owner}-{name}"[:100]


def fingerprint(refs: dict[str, str]) -> str:
    return hashlib.sha256("\n".join(f"{r} {s}" for r, s in sorted(refs.items())).encode()).hexdigest()[:12]


def actions_off(gh: GitHub, owner: str, name: str) -> None:
    gh.must("PUT", f"/repos/{owner}/{name}/actions/permissions", {"enabled": False}, 204,
            "disabling Actions")


def set_topics(gh: GitHub, owner: str, name: str, topics: list[str]) -> None:
    gh.must("PUT", f"/repos/{owner}/{name}/topics", {"names": topics}, 200, "tagging")


def sync(repo: dict, gitea: Gitea, gh: GitHub, git: Git, owner: str, server: str,
         cache: Path) -> str:
    full = repo["full_name"]
    name = mirror_name(full)
    # The ownership mark: set when the mirror is created, and naming its exact
    # source, so neither an unrelated repo nor another Gitea repo's mirror is
    # ever pushed over.
    marker = f"Read-only mirror of {full} from Gitea. Pushes here are overwritten."

    status, target = gh.call("GET", f"/repos/{owner}/{name}")
    created = status == 404
    if created:
        target = gh.must("POST", "/user/repos", {
            "name": name,
            "private": True,
            "description": marker,
            "has_issues": False,
            "has_projects": False,
            "has_wiki": False,
            "auto_init": False,
        }, 201, "creating the repo")
        name = target["name"]
        actions_off(gh, owner, name)
    elif status != 200:
        raise Fail(f"looking up the mirror failed (HTTP {status})")
    elif not target.get("private"):
        raise Fail("conflict: a public GitHub repo has this mirror's name; not touching it")
    elif target.get("description") != marker:
        raise Fail("conflict: a GitHub repo that isn't this mirror has its name; not touching it")

    topics = target.get("topics") or []
    keep = [t for t in topics if not t.startswith(FAILING)]
    keep += [] if TOPIC in keep else [TOPIC]

    src_url = f"{gitea.url}/{full}.git"
    dst_url = f"{server.rstrip('/')}/{owner}/{name}.git"
    src = git.refs(src_url)
    mark = FAILING + fingerprint(src)
    if mark in topics and not RETRY_FAILED:
        return "still failing"

    try:
        dst = {} if created else git.refs(dst_url)
        result = transfer(repo, gh, git, owner, name, src_url, dst_url, src, dst, created, cache)
    except Fail:
        # Remember the failure against this exact upstream state, so the next
        # runs skip it until Gitea changes instead of retrying a full upload.
        try:
            set_topics(gh, owner, name, keep + [mark])
        except Fail:
            pass
        raise
    if sorted(topics) != sorted(keep):
        set_topics(gh, owner, name, keep)
    return result


def transfer(repo: dict, gh: GitHub, git: Git, owner: str, name: str, src_url: str,
             dst_url: str, src: dict, dst: dict, created: bool, cache: Path) -> str:
    if src == dst:
        return "created (empty)" if created else "unchanged"

    if not created:
        actions_off(gh, owner, name)  # in case someone switched it back on
    if not src:
        shutil.rmtree(cache, ignore_errors=True)  # nothing upstream: push from empty
    if not (cache / "HEAD").exists():
        shutil.rmtree(cache, ignore_errors=True)
        git("init", "--bare", "--quiet", str(cache))
    try:
        if src:
            git("-C", str(cache), "fetch", "--quiet", "--prune", src_url, *REFSPECS)
            git("-C", str(cache), "push", "--quiet", dst_url, *REFSPECS)

        # Before pruning: GitHub refuses to delete its current default branch,
        # so a renamed default upstream has to be switched over first.
        default = repo.get("default_branch")
        if default and f"refs/heads/{default}" in src:
            current = gh.must("GET", f"/repos/{owner}/{name}", None, 200, "reading the mirror")
            if current.get("default_branch") != default:
                gh.must("PATCH", f"/repos/{owner}/{name}", {"default_branch": default}, 200,
                        "setting the default branch")

        stale = {ref for ref in dst if not ref.endswith("^{}")} - src.keys()
        if stale:
            git("-C", str(cache), "push", "--quiet", "--prune", dst_url, *REFSPECS)
    except Fail as exc:
        if "fetch" in str(exc):  # a broken fetch may have left the cache half-done
            shutil.rmtree(cache, ignore_errors=True)
        raise
    return "created" if created else "updated"


# ---------------------------------------------------------------------------


def cache_root() -> tuple[Path, bool]:
    """(directory, persistent?). On the runner the tool cache survives between
    jobs; anywhere else a throwaway directory keeps runs self-contained."""
    configured = os.environ.get("MIRROR_CACHE") or (
        os.path.join(os.environ["RUNNER_TOOL_CACHE"], "gitea-mirror")
        if os.environ.get("RUNNER_TOOL_CACHE") else "")
    if configured:
        Path(configured).mkdir(parents=True, exist_ok=True)
        return Path(configured), True
    return Path(tempfile.mkdtemp(prefix="gitea-mirror-")), False


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)  # show progress live, not at exit
    missing = [k for k in ("GITEA_URL", "GITEA_TOKEN", "MIRROR_TOKEN") if not os.environ.get(k)]
    if missing:
        print(f"::error::missing secrets: {', '.join(missing)}")
        return 1
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    gitea = Gitea(os.environ["GITEA_URL"], os.environ["GITEA_TOKEN"])
    gh = GitHub(os.environ.get("GITHUB_API_URL", "https://api.github.com"), os.environ["MIRROR_TOKEN"])
    git = Git(git_env(gitea.url, os.environ["GITEA_TOKEN"], server, os.environ["MIRROR_TOKEN"]))

    if not gitea.reachable():
        print("::error::Gitea is unreachable. Is the runner on the tailnet, and does the "
              "tailnet policy let it through to the bridge?")
        return 1
    status, me = gh.call("GET", "/user")
    if status != 200:
        print(f"::error::GitHub rejected MIRROR_TOKEN (HTTP {status})")
        return 1
    owner = me["login"]

    try:
        repos = sorted(gitea.repos(), key=lambda r: r["full_name"].lower())
    except Fail as exc:
        print(f"::error::{exc}")
        return 1
    root, persistent = cache_root()
    print(f"{len(repos)} Gitea repos{', retrying failed ones' if RETRY_FAILED else ''}")

    counts: Counter[str] = Counter()
    claimed: set[str] = set()
    for repo in repos:
        full = repo["full_name"]
        if repo.get("mirror") and SKIP_PULL_MIRRORS:
            counts["skipped (Gitea pull mirror)"] += 1
            continue
        if mirror_name(full).lower() in claimed:
            counts["failed"] += 1
            print(f"::error::{rid(full)}: conflict: another Gitea repo maps to the same GitHub name")
            continue
        claimed.add(mirror_name(full).lower())
        try:
            result = sync(repo, gitea, gh, git, owner, server, root / f"{rid(full)}.git")
        except Fail as exc:
            counts["failed"] += 1
            print(f"::error::{rid(full)}: {exc}")
            continue
        except Exception as exc:  # one bad repo mustn't stop the rest
            counts["failed"] += 1
            print(f"::error::{rid(full)}: unexpected {type(exc).__name__}")
            continue
        counts[result] += 1
        if result == "still failing":
            print(f"::warning::{rid(full)}: failed before and nothing changed in Gitea since; "
                  "skipped (run by hand with \"retry failed\" to try again)")
        elif result != "unchanged":
            print(f"  {rid(full)} {result}")

    if persistent:  # drop the cache of repos that are gone from Gitea
        live = {f"{rid(r['full_name'])}.git" for r in repos}
        for stale in root.glob("*.git"):
            if stale.name not in live:
                shutil.rmtree(stale, ignore_errors=True)
    else:
        shutil.rmtree(root, ignore_errors=True)

    print(", ".join(f"{n} {what}" for what, n in sorted(counts.items())) or "nothing to do")
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
