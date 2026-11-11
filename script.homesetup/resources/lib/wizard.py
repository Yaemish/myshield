"""Home Setup Wizard: installs repos and add-ons, applies settings, overlays userdata, switches skin."""
import glob
import json
import os
import shutil
import time
import zipfile

import xbmc
import xbmcgui
import xbmcvfs

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.abspath(os.path.join(HERE, ".."))
ADDONS_DIR = xbmcvfs.translatePath("special://home/addons")
USERDATA = xbmcvfs.translatePath("special://profile")
ADDON_DATA = os.path.join(USERDATA, "addon_data")

monitor = xbmc.Monitor()


def log(msg):
    xbmc.log("[script.homesetup] " + str(msg), xbmc.LOGINFO)


def jsonrpc(method, params=None):
    req = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    return json.loads(xbmc.executeJSONRPC(json.dumps(req)))


def set_setting(setting_id, value):
    res = jsonrpc("Settings.SetSettingValue", {"setting": setting_id, "value": value})
    ok = "error" not in res
    log("setting %s=%r -> %s" % (setting_id, value, "ok" if ok else res.get("error")))
    return ok


def has_addon(addon_id):
    return xbmc.getCondVisibility("System.HasAddon(%s)" % addon_id)


def confirm_dialogs():
    """Accept Kodi's own yes/no prompts (dependency lists, keep-skin) while we wait."""
    if xbmc.getCondVisibility("Window.IsActive(yesnodialog)"):
        xbmc.executebuiltin("SendClick(11)")


def wait_until(predicate, timeout, interval=1.0):
    end = time.time() + timeout
    while time.time() < end and not monitor.abortRequested():
        if predicate():
            return True
        confirm_dialogs()
        if monitor.waitForAbort(interval):
            break
    return predicate()


def install_repo_zip(repo_id):
    matches = sorted(glob.glob(os.path.join(RES, "repos", repo_id + "-*.zip")))
    if not matches:
        log("no bundled zip for " + repo_id)
        return False
    with zipfile.ZipFile(matches[-1]) as zf:
        zf.extractall(ADDONS_DIR)
    xbmc.executebuiltin("UpdateLocalAddons")
    wait_until(lambda: has_addon(repo_id), 20)
    jsonrpc("Addons.SetAddonEnabled", {"addonid": repo_id, "enabled": True})
    xbmc.executebuiltin("UpdateAddonRepos")
    return has_addon(repo_id)


def install_addon(addon_id, timeout=240):
    if has_addon(addon_id):
        return True
    xbmc.executebuiltin("InstallAddon(%s)" % addon_id)
    return wait_until(lambda: has_addon(addon_id), timeout)


def clean_slate(cfg):
    # Move off the managed skin first so its settings are not live when deleted.
    if xbmc.getSkinDir() == cfg["skin"]:
        set_setting("lookandfeel.skin", cfg["fallback_skin"])
        wait_until(lambda: xbmc.getSkinDir() == cfg["fallback_skin"], 30)
    for addon_id in cfg["clean_slate_addon_data"]:
        path = os.path.join(ADDON_DATA, addon_id)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
            log("removed " + path)


def ask_share():
    dlg = xbmcgui.Dialog()
    if not dlg.yesno("Home Setup", "Set up your media server share now?[CR]Choose No to skip and fill it in later."):
        return {"{{MOVIES_URL}}": "", "{{TV_URL}}": ""}
    host = dlg.input("Server address (e.g. 192.168.1.10)")
    user = dlg.input("Username")
    pwd = dlg.input("Password", option=xbmcgui.ALPHANUM_HIDE_INPUT)
    movies = dlg.input("Movies share path (e.g. Movies)")
    tv = dlg.input("TV share path (e.g. TV)")
    auth = ("%s:%s@" % (user, pwd)) if user else ""

    def url(p):
        return "smb://%s%s/%s/" % (auth, host, p.strip("/")) if host and p else ""

    return {"{{MOVIES_URL}}": url(movies), "{{TV_URL}}": url(tv)}


def apply_overlay(tokens):
    root = os.path.join(RES, "overlay")
    count = 0
    for base, _dirs, files in os.walk(root):
        for name in files:
            if name == "README.txt" and base == root:
                continue
            src = os.path.join(base, name)
            dst = os.path.join(USERDATA, os.path.relpath(src, root))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            try:
                with open(src, "r", encoding="utf-8") as fh:
                    text = fh.read()
                for key, val in tokens.items():
                    text = text.replace(key, val)
                with open(dst, "w", encoding="utf-8") as fh:
                    fh.write(text)
            except UnicodeDecodeError:
                shutil.copyfile(src, dst)
            count += 1
    log("overlay files copied: %d" % count)
    return count


def run():
    with open(os.path.join(RES, "config.json"), encoding="utf-8") as fh:
        cfg = json.load(fh)
    dlg = xbmcgui.Dialog()
    if not dlg.yesno("Home Setup", "Install and configure everything now?[CR]This can take a few minutes."):
        return
    wipe = dlg.yesno("Home Setup", "Clean slate? This resets settings for the add-ons and skin this setup manages. Other add-ons and your library are untouched.")
    tokens = ask_share()
    problems = []

    progress = xbmcgui.DialogProgress()
    progress.create("Home Setup", "Starting...")
    try:
        # Enable unknown sources first so third-party repos install without prompts.
        for item in cfg["settings"][:2]:
            set_setting(item["id"], item["value"])

        if wipe:
            progress.update(5, "Resetting managed settings...")
            clean_slate(cfg)

        for i, repo_id in enumerate(cfg["repos"]):
            progress.update(10 + i * 10, "Installing repository %s..." % repo_id)
            if not install_repo_zip(repo_id):
                problems.append("repo " + repo_id)

        for i, addon_id in enumerate(cfg["addons"]):
            progress.update(35 + i * 20, "Installing %s..." % addon_id)
            if not install_addon(addon_id):
                problems.append("add-on " + addon_id)

        progress.update(80, "Applying settings...")
        apply_overlay(tokens)
        for item in cfg["settings"][2:]:
            if not set_setting(item["id"], item["value"]):
                problems.append("setting " + item["id"])

        progress.update(92, "Switching skin...")
        if has_addon(cfg["skin"]):
            set_setting("lookandfeel.skin", cfg["skin"])
            wait_until(lambda: xbmc.getSkinDir() == cfg["skin"], 60)
        else:
            problems.append("skin " + cfg["skin"] + " not installed")
    finally:
        progress.close()

    if problems:
        dlg.ok("Home Setup finished with issues", "Could not complete:[CR]" + "[CR]".join(problems))
    else:
        dlg.ok("Home Setup", "Done. Restart Kodi once to finish loading the new skin.")
