"""Publish the reviewed project using the existing Git credential helper.

Credentials stay in process memory. No credential is written into the repository.
"""
import json
import os
from pathlib import Path
import subprocess

import requests

ROOT = Path(__file__).resolve().parents[1]
OWNER = "MichaelWangGo"
NAME = "crcd-instrument-keypoints"
PAGE = f"https://{OWNER.lower()}.github.io/{NAME}/"


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, text=True, capture_output=True).stdout.strip()


def main():
    qa = json.loads((ROOT / "qa-results/report.json").read_text())
    assert qa["passed"], "Local browser QA must pass before publishing"
    result = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                            capture_output=True, text=True, check=True,
                            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    credentials = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    session = requests.Session()
    session.headers.update({"Authorization": "Bearer " + credentials["password"],
                            "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})

    def api(method, path, **kwargs):
        response = session.request(method, "https://api.github.com" + path, timeout=45, **kwargs)
        if not response.ok:
            raise RuntimeError(f"GitHub {method} {path}: {response.status_code} {response.text[:500]}")
        return response.json() if response.content else {}

    user = api("GET", "/user")
    assert user["login"] == OWNER
    record = ROOT / "publication.json"
    if record.exists():
        publication = json.loads(record.read_text())
        repo = api("GET", f"/repos/{OWNER}/{NAME}")
        assert repo["id"] == publication["repository_id"]
    else:
        repo = api("POST", "/user/repos", json={"name": NAME, "private": False, "auto_init": False,
                   "description": "Interactive CRCD surgical instrument keypoint visualization with ViTPose++ and complete test metrics",
                   "homepage": PAGE})
        publication = {"repository_id": repo["id"], "repository_url": repo["html_url"], "page_url": PAGE}
        record.write_text(json.dumps(publication, indent=2))
    if not (ROOT / ".git").exists():
        git("init", "-b", "main")
        git("config", "user.name", user.get("name") or OWNER)
        git("config", "user.email", f'{user["id"]}+{OWNER}@users.noreply.github.com')
        git("remote", "add", "origin", repo["clone_url"])
    git("add", ".")
    if git("diff", "--cached", "--name-only"):
        git("commit", "-m", "Publish measured CRCD instrument keypoint visualization")
    git("push", "-u", "origin", "main")
    status = session.get(f"https://api.github.com/repos/{OWNER}/{NAME}/pages", timeout=30)
    if status.status_code == 404:
        pages = api("POST", f"/repos/{OWNER}/{NAME}/pages", json={"source": {"branch": "main", "path": "/docs"}})
    else:
        status.raise_for_status()
        pages = status.json()
    publication.update({"commit": git("rev-parse", "HEAD"), "pages_status": pages.get("status"),
                        "page_url": pages.get("html_url", PAGE), "source": pages.get("source")})
    record.write_text(json.dumps(publication, indent=2))
    print(json.dumps(publication, indent=2))


if __name__ == "__main__":
    main()
