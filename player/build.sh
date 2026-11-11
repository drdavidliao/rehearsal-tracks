#!/bin/zsh
# Builds "build/Rehearsal Player.app" here. Needs Xcode's tools and: brew install rubberband
set -e
cd "$(dirname "$0")"
swift build -c release --product RehearsalPlayer 2>&1 | grep -v "built for newer 'macOS'"
APP="build/Rehearsal Player.app"
rm -rf "$APP"; mkdir -p "$APP/Contents/MacOS"
cp .build/release/RehearsalPlayer "$APP/Contents/MacOS/Rehearsal Player"
mkdir -p "$APP/Contents/Resources"; cp AppIcon.icns "$APP/Contents/Resources/"
cat > "$APP/Contents/Info.plist" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>Rehearsal Player</string>
<key>CFBundleExecutable</key><string>Rehearsal Player</string>
<key>CFBundleIdentifier</key><string>local.rehearsal.player</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleIconFile</key><string>AppIcon</string>
<key>CFBundleShortVersionString</key><string>0.1</string>
<key>LSMinimumSystemVersion</key><string>13.0</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PL
codesign --force --sign - "$APP"
echo "built $PWD/$APP"
