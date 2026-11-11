#!/usr/bin/env python3
"""Build the installer ZIP and a tiny GitHub Pages site.

Run in GitHub Actions (needs network to fetch the third-party repo ZIPs).
Use --offline to skip fetching, e.g. for a quick local packaging test.
"""
import hashlib
import io
import re
import shutil
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ADDON = ROOT / "script.homesetup"
DIST = ROOT / "dist"
SITE = DIST / "site"

# repo add-on id -> page that links to its installable ZIP
SOURCES = {
    "repository.kodifitzwell": "https://kodifitzwell.github.io/repo/",
    "repository.jurialmunkey": "https://jurialmunkey.github.io/repository.jurialmunkey/",
}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "kodi-installer-build"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def vkey(name):
    return tuple(int(x) for x in re.findall(r"\d+", name.rsplit("-", 1)[-1]))


def resolve_zip(repo_id, index_url):
    html = fetch(index_url).decode("utf-8", "replace")
    names = set(re.findall(r'href="([^"]*?%s-[\d.]+\.zip)"' % re.escape(repo_id), html))
    if not names:
        sys.exit("No %s-*.zip link found at %s" % (repo_id, index_url))
    best = max(names, key=lambda n: vkey(n))
    url = best if best.startswith("http") else index_url.rstrip("/") + "/" + best.lstrip("/")
    return url, Path(best).name


def verify_repo_zip(data, repo_id):
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        root = ET.fromstring(zf.read("%s/addon.xml" % repo_id))
    if root.get("id") != repo_id:
        sys.exit("ZIP addon.xml id %r != expected %r" % (root.get("id"), repo_id))


def main():
    offline = "--offline" in sys.argv
    shutil.rmtree(DIST, ignore_errors=True)
    stage = DIST / "stage" / "script.homesetup"
    shutil.copytree(ADDON, stage, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (stage / "resources" / "repos").mkdir(parents=True, exist_ok=True)

    notes = []
    if not offline:
        for repo_id, index in SOURCES.items():
            url, name = resolve_zip(repo_id, index)
            data = fetch(url)
            verify_repo_zip(data, repo_id)
            (stage / "resources" / "repos" / name).write_bytes(data)
            notes.append("%s  %s  %s" % (hashlib.sha256(data).hexdigest(), name, url))
            print("bundled", name)

    version = ET.parse(ADDON / "addon.xml").getroot().get("version")
    SITE.mkdir(parents=True, exist_ok=True)
    zip_name = "script.homesetup-%s.zip" % version
    with zipfile.ZipFile(SITE / zip_name, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(stage.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(stage.parent).as_posix())
    (SITE / "index.html").write_text('<a href="%s">%s</a>\n' % (zip_name, zip_name))
    (SITE / "BUNDLED.txt").write_text("\n".join(notes) + "\n")
    print("built", SITE / zip_name)


if __name__ == "__main__":
    main()
