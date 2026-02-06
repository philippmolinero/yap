#!/bin/bash
set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$APP_DIR/.venv"
CONFIG_DIR="$HOME/.config/yap"
OLD_CONFIG_DIR="$HOME/.config/voxtral-dictation"
PLIST_NAME="com.yap-dictation"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

echo "=== Yap — Install ==="
echo ""

# 1. Create virtual environment
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
else
    echo "Virtual environment already exists."
fi

# 2. Install dependencies
echo "Installing dependencies..."
"$VENV_DIR/bin/pip" install -q --upgrade pip
"$VENV_DIR/bin/pip" install -q -r "$APP_DIR/requirements.txt"

# 3. Migrate old config directory if needed
if [ -d "$OLD_CONFIG_DIR" ] && [ ! -d "$CONFIG_DIR" ]; then
    echo "Migrating config from $OLD_CONFIG_DIR to $CONFIG_DIR..."
    mv "$OLD_CONFIG_DIR" "$CONFIG_DIR"
fi

# 4. Set up config directory
mkdir -p "$CONFIG_DIR"

if [ ! -f "$CONFIG_DIR/config.toml" ]; then
    cp "$APP_DIR/config/default.toml" "$CONFIG_DIR/config.toml"
    echo "Created config at $CONFIG_DIR/config.toml"
else
    echo "Config already exists at $CONFIG_DIR/config.toml"
fi

if [ ! -f "$CONFIG_DIR/vocabulary.txt" ]; then
    cp "$APP_DIR/config/vocabulary.txt" "$CONFIG_DIR/vocabulary.txt"
    echo "Created vocabulary at $CONFIG_DIR/vocabulary.txt"
else
    echo "Vocabulary already exists at $CONFIG_DIR/vocabulary.txt"
fi

# 5. Check .env
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    echo ""
    echo "!! Created .env from template. You MUST add your API keys:"
    echo "   $APP_DIR/.env"
    echo ""
fi

# 6. Create launchd plist
cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${VENV_DIR}/bin/python3</string>
        <string>-m</string>
        <string>app.main</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${APP_DIR}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>${APP_DIR}/logs/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${APP_DIR}/logs/stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
EOF

mkdir -p "$APP_DIR/logs"

echo ""
echo "=== Install complete ==="
echo ""
echo "To start now:  launchctl load $PLIST_PATH"
echo "To stop:       launchctl unload $PLIST_PATH"
echo "Logs:          $APP_DIR/logs/"
echo ""
echo "The app will auto-start on login."
echo ""
echo "Required macOS permissions (System Settings > Privacy & Security):"
echo "  - Input Monitoring: grant to Python or Terminal"
echo "  - Microphone: grant to Python or Terminal"
echo "  - Accessibility: grant to Python or Terminal"
