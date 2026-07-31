#!/usr/bin/env bash
# scripts/generate_release_keystore.sh
#
# Interactive helper for creating the internal-signing keystore used by
# Stage 3's Release APK. Runs in WSL (or any Linux with keytool).
#
# What it does:
#   1. Prompts for CN/OU/O/L/ST/C (distinguished name) and keystore/key passwords.
#   2. Invokes `keytool -genkeypair` with -validity 10000 days.
#   3. Writes buildozer.spec.local (gitignored) so the signing config is
#      picked up by scripts/wsl_build_android.sh release path.
#
# What it does NOT do:
#   - Store or transmit the keystore password anywhere except buildozer.spec.local.
#   - Copy the keystore file itself into the repo (~/keys/ is your responsibility).
#   - Upload anything to the internet.
#
# Non-goal: this is the INTERNAL signing keystore, NOT a positive
# publish-channel identity. See docs/release-notes.md §1 for the five-step
# switchover before public release.

set -euo pipefail

# buildozer.spec.local path — resolved relative to the script location so the
# helper works both in the WSL workspace copy and from /mnt/d/.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SPEC_LOCAL="$PROJECT_ROOT/buildozer.spec.local"

# Default keystore lives inside the project's `keys/` directory. `.gitignore`
# has a directory-level `keys/` rule so nothing under it is ever tracked. If
# you prefer a location outside the project tree (recommended for long-term
# storage), set KEYSTORE_DIR before invoking the script.
KEYSTORE_DIR="${KEYSTORE_DIR:-$PROJECT_ROOT/keys}"
KEYSTORE_FILE="${KEYSTORE_FILE:-$KEYSTORE_DIR/reversiblemosaic.jks}"
KEY_ALIAS="${KEY_ALIAS:-reversiblemosaic}"
VALIDITY_DAYS=10000
KEY_SIZE=2048
KEY_ALGORITHM="RSA"

if ! command -v keytool >/dev/null 2>&1; then
    echo "[error] keytool not found. Install OpenJDK 17 first:" >&2
    echo "        sudo apt install openjdk-17-jdk" >&2
    exit 1
fi

if [ -f "$KEYSTORE_FILE" ]; then
    echo "[warn] $KEYSTORE_FILE already exists."
    echo "       If you regenerate, any APK previously signed with the old key"
    echo "       becomes unusable for upgrade. Overwrite? [y/N]"
    read -r reply
    case "$reply" in
        y|Y|yes|YES) rm -f "$KEYSTORE_FILE" ;;
        *) echo "[abort] keeping existing keystore."; exit 0 ;;
    esac
fi

mkdir -p "$KEYSTORE_DIR"
chmod 700 "$KEYSTORE_DIR"

echo "==========================================================="
echo "ReversibleMosaic 内部签名 keystore 生成器"
echo "==========================================================="
echo
echo "本脚本将在你本机生成一个 RSA-$KEY_SIZE keystore，有效期 $VALIDITY_DAYS 天。"
echo "  路径：$KEYSTORE_FILE"
echo "  别名：$KEY_ALIAS"
echo
echo "keystore 与口令绝不会离开你的机器。密钥文件不会入 git 仓库。"
echo "口令仅会写到 buildozer.spec.local（.gitignore 已排除）。"
echo
echo "⚠️ 重要：这是 INTERNAL 自签 keystore。正式面向公开用户发布前必须换"
echo "     成正式发布身份（见 docs/release-notes.md §1）。同 keystore 一"
echo "     旦丢失，同 applicationId 的老用户将无法再收到升级。请立即备份"
echo "     $KEYSTORE_FILE 到离线安全位置。"
echo
echo "==========================================================="

read -r -p "签名主体 CN (Common Name, 你的名字 / 组织名): " DN_CN
read -r -p "组织单位 OU (可留空): " DN_OU
read -r -p "组织 O (可留空): " DN_O
read -r -p "城市 L (例: Shanghai / Beijing / 可留空): " DN_L
read -r -p "省份 ST (例: SH / BJ / 可留空): " DN_ST
read -r -p "国家 C (2 字母 ISO 代码, 例: CN): " DN_C

# Assemble DN, skipping empty fields.
DN=""
[ -n "$DN_CN" ] && DN="CN=$DN_CN"
[ -n "$DN_OU" ] && DN="$DN, OU=$DN_OU"
[ -n "$DN_O" ] && DN="$DN, O=$DN_O"
[ -n "$DN_L" ] && DN="$DN, L=$DN_L"
[ -n "$DN_ST" ] && DN="$DN, ST=$DN_ST"
[ -n "$DN_C" ] && DN="$DN, C=$DN_C"

if [ -z "$DN" ]; then
    echo "[error] 至少填写 CN。" >&2
    exit 1
fi

echo
echo "签名主体 DN: $DN"
echo
echo "接下来 keytool 会分别索取 [keystore 口令] 与 [key 口令] —— 两者建议"
echo "设成相同值，长度 ≥ 8 位。请自行选择并牢记；本脚本不会保存。"
echo

# Let keytool prompt interactively for passwords (safer than piping).
keytool -genkeypair \
    -alias "$KEY_ALIAS" \
    -keyalg "$KEY_ALGORITHM" \
    -keysize "$KEY_SIZE" \
    -validity "$VALIDITY_DAYS" \
    -keystore "$KEYSTORE_FILE" \
    -storetype JKS \
    -dname "$DN"

echo
echo "==========================================================="
echo "keystore 已生成。keytool -list 验证："
echo "==========================================================="
keytool -list -v -keystore "$KEYSTORE_FILE" -alias "$KEY_ALIAS" || true

echo
echo "==========================================================="
echo "生成 buildozer.spec.local"
echo "==========================================================="
echo
echo "为了让 scripts/wsl_build_android.sh 的 release 路径能自动签名，需要把"
echo "keystore 路径 + 口令写到 $SPEC_LOCAL。"
echo "该文件已在 .gitignore 排除，绝不入库。"
echo
read -r -s -p "再输入一次 keystore 口令用于写入 spec.local: " KEYSTORE_PWD
echo
read -r -s -p "再输入一次 key 口令用于写入 spec.local: " KEY_PWD
echo

# NOTE: buildozer.spec.local overrides buildozer.spec on a per-key basis.
# Fields below are consumed by python-for-android's signing config when
# `buildozer android release` is invoked.
cat > "$SPEC_LOCAL" <<EOF
# buildozer.spec.local — LOCAL SIGNING CONFIG, DO NOT COMMIT.
# Auto-generated by scripts/generate_release_keystore.sh on $(date -u '+%Y-%m-%dT%H:%M:%SZ').
#
# python-for-android's signing config keys are:
#   android.release_keystore   — path to the .jks file
#   android.release_keyalias   — key alias inside the keystore
#   android.release_keystore_passwd — keystore password
#   android.release_keyalias_passwd — key alias password
#
# All four MUST be present for buildozer android release to produce a signed APK.

[app]
android.release_keystore = $KEYSTORE_FILE
android.release_keyalias = $KEY_ALIAS
android.release_keystore_passwd = $KEYSTORE_PWD
android.release_keyalias_passwd = $KEY_PWD
EOF
chmod 600 "$SPEC_LOCAL"

echo "[ok] wrote $SPEC_LOCAL (chmod 600)"
echo
echo "==========================================================="
echo "完成"
echo "==========================================================="
echo
echo "现在你可以跑 Release 构建（Stage 3 Block 3 起两参数都强制）："
echo "  wsl -d Ubuntu -e bash /mnt/d/python/python_projects/ReversibleMosaic/scripts/wsl_build_android.sh release v18"
echo
echo "构建产物（脚本自动加版本后缀 + 拷回 D 盘 + apksigner 签名）："
echo "  ~/src/ReversibleMosaic/bin/reversiblemosaic-0.1.0-arm64-v8a-release-v18.apk"
echo "  /mnt/d/python/python_projects/ReversibleMosaic/bin/reversiblemosaic-0.1.0-arm64-v8a-release-v18.apk"
echo
echo "⚠️  关键提醒 —— keystore 备份"
echo "  keystore 当前在项目目录内：$KEYSTORE_FILE"
echo "  .gitignore 已挡住 keys/ 目录，不会入库；但项目目录仍可能被："
echo "    * OneDrive / iCloud / 云盘同步（gitignore 不管这些）"
echo "    * rm -rf 项目重建时误删"
echo "    * 压缩打包 / 截图 / 发给别人时误分享"
echo "  请立即再拷一份到项目外的位置："
echo "    * 离线 U 盘（推荐，物理隔离）"
echo "    * 密码管理器附件（Bitwarden / 1Password 支持）"
echo "    * WSL 家目录外的加密卷"
echo "  keystore 丢 = 同 applicationId 永远发不出升级。"
echo
echo "其他叮嘱："
echo "  * 不要把 $SPEC_LOCAL 或 keystore 加进 git commit"
echo "  * 正式发布前完成 docs/release-notes.md §1 的身份切换五步"
