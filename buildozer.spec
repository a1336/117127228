[app]
title = 星际矿工
package.name = starminer
package.domain = org.dsh
source.dir = .
source.include_exts = py,png
source.exclude_dirs = .github, bin, .buildozer, __pycache__
source.exclude_patterns = savegame.json, game_error.log, *.zip, README_APK.md, build.yml
version = 1.0
requirements = python3,pygame
orientation = portrait
fullscreen = 1
icon.filename = %(source.dir)s/icon.png
android.api = 31
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a
android.accept_sdk_license = True
android.release_artifact = apk
p4a.branch = v2023.05.21

[buildozer]
log_level = 2
warn_on_root = 1
