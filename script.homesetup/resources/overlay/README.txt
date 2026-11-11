Files in this folder are copied into Kodi's userdata folder before the skin is switched.
Example: overlay/addon_data/plugin.video.pov/settings.xml -> userdata/addon_data/plugin.video.pov/settings.xml

Text files may contain these tokens, which the wizard replaces with what the user types at setup:
  {{MOVIES_URL}}   e.g. smb://user:pass@192.168.1.10/Movies/
  {{TV_URL}}       e.g. smb://user:pass@192.168.1.10/TV/

Nothing is shipped here yet on purpose. The POV folder-source setting names and the Arctic Fuse 3
home menu / widget files (script.skinshortcuts, script.skinvariables) must come from a real,
working install, not from guesses. Drop exported files in this folder structure and rebuild.
