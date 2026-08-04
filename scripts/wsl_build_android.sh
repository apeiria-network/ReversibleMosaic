#!/usr/bin/env bash
# Convenience script: run inside WSL to build the Android APK (debug or release).
#
# Usage:
#   wsl_build_android.sh <mode> <version>
#     <mode>    : debug | release  (required, no default)
#     <version> : v<digits>        (required, e.g. v18)
#
# 例：
#   wsl_build_android.sh debug   v18
#   wsl_build_android.sh release v18
#
# Debug 与 Release 产物文件名都会带 -<version> 后缀，落到：
#   WSL   : ~/src/ReversibleMosaic/bin/reversiblemosaic-0.1.0-arm64-v8a-<mode>-<version>.apk
#   D 盘 : /mnt/d/python/python_projects/ReversibleMosaic/bin/  同名
# 目标文件若已存在，脚本报错退出（不覆盖，避免误替换已发出的 APK）。
#
# Release 分支的签名策略（stage3-block3-problems.md Q1 决策 C）：
#   - buildozer.spec.local 只保留在 D 盘（rsync 已排除），WSL 侧永远没有；
#   - WSL 侧 buildozer android release 因此产出 unsigned APK；
#   - 本脚本用 apksigner 直接签名，口令通过 stdin heredoc 传入
#     (--ks-pass stdin --key-pass stdin)，不落 cmdline、不进日志；
#   - 签完立即 unset 口令变量；出错也会通过 trap 兜底清理；
#   - 不做 zipalign（Q7：暂不引入独立对齐步骤，apksigner v2/v3 自身足够）。
set -euo pipefail

# --------- 参数解析 ---------
usage() {
    cat >&2 <<USAGE
usage: $0 <debug|release> <version>
       <version> must match ^v[0-9]+$   (例: v18)
example:
       $0 debug   v18
       $0 release v18
USAGE
    exit 2
}

BUILD_MODE="${1:-}"
BUILD_VERSION="${2:-}"

case "$BUILD_MODE" in
    debug|release) ;;
    "") echo "[error] missing <mode>" >&2; usage ;;
    *)  echo "[error] unknown build mode: $BUILD_MODE (expected: debug|release)" >&2; usage ;;
esac

if [ -z "$BUILD_VERSION" ]; then
    echo "[error] missing <version>" >&2
    usage
fi
if ! [[ "$BUILD_VERSION" =~ ^v[0-9]+$ ]]; then
    echo "[error] version must match ^v[0-9]+$, got: $BUILD_VERSION" >&2
    usage
fi

# --------- 路径常量 ---------
WORKSPACE="/home/hydrogen/src/ReversibleMosaic"
BUILD_VENV="/home/hydrogen/.venvs/reversible-mosaic-build"
LOG="/home/hydrogen/src/reversible-mosaic-build.log"
P4A_CACHE="${P4A_CACHE:-$HOME/.p4a-source-cache}"
P4A_PACKAGES_DIR="$WORKSPACE/.buildozer/android/platform/build-arm64-v8a/packages"

# D 盘 (Windows) 只读引用路径 —— 签名凭据与 keystore 都从这里现拉现用。
DRIVE_ROOT="/mnt/d/python/python_projects/ReversibleMosaic"
SPEC_LOCAL_DRIVE="$DRIVE_ROOT/buildozer.spec.local"
DRIVE_BIN="$DRIVE_ROOT/bin"

# 目标 APK 命名（package.name=reversiblemosaic, version=0.1.0, arch=arm64-v8a）
APK_STEM="reversiblemosaic-0.1.0-arm64-v8a-${BUILD_MODE}-${BUILD_VERSION}"
FINAL_APK_WSL="$WORKSPACE/bin/${APK_STEM}.apk"
FINAL_APK_DRIVE="$DRIVE_BIN/${APK_STEM}.apk"

# 拒绝覆盖：任一目标位置已存在 → 报错退出。
# 同 version 下 debug 与 release 因 -<mode>- 段不同不会冲突（v18 debug + v18 release 可共存）。
for existing in "$FINAL_APK_WSL" "$FINAL_APK_DRIVE"; do
    if [ -e "$existing" ]; then
        echo "[error] target APK already exists: $existing" >&2
        echo "        refuse to overwrite. Delete it or bump version." >&2
        exit 4
    fi
done

# Release 分支前置检查：D 盘 spec.local 必须存在。
if [ "$BUILD_MODE" = "release" ]; then
    if [ ! -f "$SPEC_LOCAL_DRIVE" ]; then
        echo "[error] release build requested but $SPEC_LOCAL_DRIVE missing." >&2
        echo "        Run scripts/generate_release_keystore.sh first." >&2
        exit 3
    fi
fi

# --------- 清残留进程 ---------
MY_PID=$$
# Kill leftover buildozer/p4a processes but never this shell or our caller.
# NOTE: match the actual executables/module names, NOT the bare word
# "buildozer" — otherwise any parent shell whose command line mentions the
# word (e.g., log file paths like /tmp/buildozer_v16.log) gets kill -9'd
# too, taking this script down with it (exit 9). Learned the hard way
# during the v15→v16 build cycle.
if command -v pgrep >/dev/null 2>&1; then
    for pid in $(pgrep -f 'bin/buildozer|pythonforandroid\.toolchain|python-for-android' || true); do
        [ "$pid" != "$MY_PID" ] && [ "$pid" != "$PPID" ] && kill -9 "$pid" 2>/dev/null || true
    done
fi

# --------- rsync：D 盘 → WSL ---------
# 保留 $WORKSPACE/.buildozer/ 加速增量构建。keys/ 与 buildozer.spec.local 一律排除，
# 保证签名素材永远只在 D 盘（B1 隔离要求）。
mkdir -p "$WORKSPACE"
rsync -a --delete \
    --exclude ".git/" \
    --exclude ".venv/" \
    --exclude ".idea/" \
    --exclude ".mypy_cache/" \
    --exclude ".pytest_cache/" \
    --exclude ".ruff_cache/" \
    --exclude ".hypothesis/" \
    --exclude "build/" \
    --exclude "bin/" \
    --exclude ".buildozer/" \
    --exclude "keys/" \
    --exclude "buildozer.spec.local" \
    --exclude "*.egg-info/" \
    /mnt/d/python/python_projects/ReversibleMosaic/ "$WORKSPACE/"

# --------- p4a 源码缓存 hard-link ---------
if [ -d "$P4A_CACHE" ]; then
    mkdir -p "$P4A_PACKAGES_DIR"
    for recipe_dir in "$P4A_CACHE"/*/; do
        recipe_name="$(basename "$recipe_dir")"
        dest="$P4A_PACKAGES_DIR/$recipe_name"
        mkdir -p "$dest"
        cp -a -f -l "$recipe_dir"/. "$dest"/
    done
    echo "[prefetch] seeded $(ls "$P4A_PACKAGES_DIR" | wc -l) recipes from $P4A_CACHE"
fi

export PATH="$BUILD_VENV/bin:$PATH"
export VIRTUAL_ENV="$BUILD_VENV"
unset PYTHONHOME

# --------- Android SDK 预检与冷恢复 ---------
# ~/.buildozer 被手动删除后，Buildozer 会先重建 sdkmanager；其首次初始化有时只留下
# 不完整的最高版本 build-tools 目录，随后因找不到 aidl 而退出。这里固定补齐本项目
# 的 Android 34 / Build-Tools 36.0.0 基线；若 sdkmanager 尚未生成，首次 buildozer
# 调用负责生成它，失败后本脚本自动补齐并只重试一次。
SDK_ROOT="$HOME/.buildozer/android/platform/android-sdk"
SDK_MANAGER="$SDK_ROOT/tools/bin/sdkmanager"
SDK_BUILD_TOOLS="$SDK_ROOT/build-tools/36.0.0"

ensure_android_sdk_baseline() {
    if [ ! -x "$SDK_MANAGER" ]; then
        echo "[sdk] sdkmanager not initialized; Buildozer will bootstrap it first"
        return 1
    fi

    echo "[sdk] ensuring build-tools 36.0.0, platform-tools, platforms;android-34"
    yes | "$SDK_MANAGER" --sdk_root="$SDK_ROOT" \
        "build-tools;36.0.0" "platform-tools" "platforms;android-34"

    # 不完整目录不能提供 aidl；删除它们可避免 Buildozer 优先选择无效的高版本。
    for candidate in "$SDK_ROOT"/build-tools/*; do
        [ -d "$candidate" ] || continue
        [ -x "$candidate/aidl" ] || {
            echo "[sdk] removing incomplete build-tools: $candidate"
            rm -rf "$candidate"
        }
    done

    if [ ! -x "$SDK_BUILD_TOOLS/aidl" ]; then
        echo "[error] Android Build-Tools 36.0.0 aidl is unavailable after SDK recovery" >&2
        return 1
    fi
}

# --------- github.com → ghfast.top 镜像 ---------
export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0="url.https://ghfast.top/https://github.com/.insteadOf"
export GIT_CONFIG_VALUE_0="https://github.com/"

cd "$WORKSPACE"
: > "$LOG"

# --------- buildozer 构建 ---------
# 注意：不能再用 exec，因为 release 分支之后还要跑 apksigner。
# 首次全局缓存恢复时 sdkmanager 尚不存在：让 Buildozer 先初始化一次；若它因缺 aidl
# 退出，补齐冻结 SDK 基线后自动重试。正常增量构建只执行一次。
run_buildozer() {
    if ensure_android_sdk_baseline; then
        buildozer android "$BUILD_MODE" 2>&1 | tee -a "$LOG"
    else
        echo "[sdk] bootstrapping SDK through Buildozer"
        first_rc=0
        buildozer android "$BUILD_MODE" 2>&1 | tee -a "$LOG" || first_rc=$?
        if [ "$first_rc" -eq 0 ]; then
            echo "[sdk] Buildozer completed during SDK bootstrap"
        else
            ensure_android_sdk_baseline
            echo "[sdk] retrying Buildozer after SDK recovery"
            buildozer android "$BUILD_MODE" 2>&1 | tee -a "$LOG"
        fi
    fi
}

# --------- 交叉编译 V1 Cython 内层 ---------
# 冷缓存下，p4a 的目标 Python headers 只会在首次 Buildozer 调用后出现。先让 helper
# 明确报告 bootstrap-required，再建立 dist、重新链接 v1.so，最后重新执行 Buildozer 把
# 已验证的 arm64 扩展装入 APK；绝不把缺少扩展的状态包装成 reference-only APK。
cython_rc=0
bash "$WORKSPACE/scripts/wsl_build_v1_cython.sh" || cython_rc=$?
case "$cython_rc" in
    0)
        ;;
    3)
        echo "[cython] bootstrapping p4a target dist before final package build"
        run_buildozer
        bash "$WORKSPACE/scripts/wsl_build_v1_cython.sh"
        ;;
    *)
        echo "[error] V1 Cython build failed (rc=$cython_rc)" >&2
        exit "$cython_rc"
        ;;
esac

run_buildozer

# --------- 后处理 ---------
mkdir -p "$WORKSPACE/bin"
mkdir -p "$DRIVE_BIN"

if [ "$BUILD_MODE" = "debug" ]; then
    PRODUCED="$WORKSPACE/bin/reversiblemosaic-0.1.0-arm64-v8a-debug.apk"
    if [ ! -f "$PRODUCED" ]; then
        echo "[error] expected debug APK not found: $PRODUCED" >&2
        exit 5
    fi
    mv -f "$PRODUCED" "$FINAL_APK_WSL"
else
    # Release: buildozer 因 WSL 侧无 spec.local，产出 -release-unsigned.apk。
    PRODUCED="$WORKSPACE/bin/reversiblemosaic-0.1.0-arm64-v8a-release-unsigned.apk"
    if [ ! -f "$PRODUCED" ]; then
        echo "[error] expected unsigned release APK not found: $PRODUCED" >&2
        echo "        Did buildozer's release build fail?" >&2
        exit 6
    fi

    # 兜底：无论后续走哪条分支，都保证口令变量在退出前被清空。
    # 先挂 trap 再赋值 —— 避免"已提取口令但 trap 尚未设置"的极短窗口。
    trap 'unset KS_PW KEY_PW 2>/dev/null || true' EXIT

    # 从 D 盘 spec.local 提取 4 项签名凭据。
    # 用 grep -m1 匹配 "key = " 起始行，然后 ${line#*=} 只按 FIRST '=' 切，
    # 保证 value 中含 '=' 的口令（如 base64 结尾）也能完整提取。
    _extract_spec() {
        local line
        line="$(grep -m1 "^$1 *= *" "$SPEC_LOCAL_DRIVE" || true)"
        [ -z "$line" ] && return 0
        local value="${line#*=}"
        # 去掉前导空格
        value="${value#"${value%%[![:space:]]*}"}"
        printf '%s' "$value"
    }
    KS_PATH="$(_extract_spec 'android.release_keystore')"
    KS_ALIAS="$(_extract_spec 'android.release_keyalias')"
    KS_PW="$(_extract_spec 'android.release_keystore_passwd')"
    KEY_PW="$(_extract_spec 'android.release_keyalias_passwd')"

    if [ -z "$KS_PATH" ] || [ -z "$KS_ALIAS" ] || [ -z "${KS_PW:-}" ] || [ -z "${KEY_PW:-}" ]; then
        # 有意不指名缺哪一项（避免暗示"哪几项已被读取"）
        echo "[error] signing config incomplete in $SPEC_LOCAL_DRIVE" >&2
        exit 7
    fi

    # 若 spec.local 里 keystore 路径写成 Windows 风格（D:\... 或 D:/...）→ 转 /mnt/d/...
    if [ ! -f "$KS_PATH" ]; then
        case "$KS_PATH" in
            [A-Za-z]:*)
                drive_letter="$(printf '%s' "$KS_PATH" | cut -c1 | tr 'A-Z' 'a-z')"
                rest="$(printf '%s' "$KS_PATH" | cut -c3-)"
                KS_PATH="/mnt/${drive_letter}${rest//\\//}"
                ;;
        esac
    fi
    if [ ! -f "$KS_PATH" ]; then
        echo "[error] keystore file not found: $KS_PATH" >&2
        exit 8
    fi

    # 找 Android SDK build-tools 下的 apksigner —— 取版本号最大的一个。
    APKSIGNER=""
    for candidate in $(ls -1 "$HOME/.buildozer/android/platform/android-sdk/build-tools" 2>/dev/null | sort -V); do
        exe="$HOME/.buildozer/android/platform/android-sdk/build-tools/$candidate/apksigner"
        [ -x "$exe" ] && APKSIGNER="$exe"
    done
    if [ -z "$APKSIGNER" ]; then
        echo "[error] apksigner not found under ~/.buildozer/android/platform/android-sdk/build-tools/" >&2
        exit 9
    fi
    echo "[wsl_build_android] using apksigner: $APKSIGNER"

    SIGNED_APK="$FINAL_APK_WSL"

    # apksigner 签名：--ks-pass stdin --key-pass stdin，两行 stdin（keystore 口令、key 口令）。
    # heredoc 通过临时 fd 喂入 apksigner 的 stdin，不留 cmdline、不进 tee 日志。
    # 有意不 tee 本命令输出到 $LOG，避免任何潜在敏感串意外落盘。
    # 明确不启用 set -x —— 会把 heredoc 展开后的口令 echo 到 stderr。
    sign_rc=0
    "$APKSIGNER" sign \
        --ks "$KS_PATH" \
        --ks-key-alias "$KS_ALIAS" \
        --ks-pass stdin \
        --key-pass stdin \
        --in "$PRODUCED" \
        --out "$SIGNED_APK" <<EOF || sign_rc=$?
$KS_PW
$KEY_PW
EOF

    # 立即清空口令变量（trap 是兜底，这里是主线）。
    unset KS_PW KEY_PW

    if [ "$sign_rc" -ne 0 ]; then
        echo "[error] apksigner sign failed (rc=$sign_rc)" >&2
        rm -f "$SIGNED_APK"
        exit 10
    fi

    # 验证签名。verify 输出仅包含证书 subject/issuer/fingerprint 等公开信息，允许落日志。
    "$APKSIGNER" verify --verbose --print-certs "$SIGNED_APK" | tee -a "$LOG"

    # 清掉未签名中间产物
    rm -f "$PRODUCED"
fi

# --------- 拷回 D 盘 + 指纹 ---------
cp -a "$FINAL_APK_WSL" "$FINAL_APK_DRIVE"

echo "[artifact] WSL    : $FINAL_APK_WSL"
sha256sum "$FINAL_APK_WSL"
echo "[artifact] D drive: $FINAL_APK_DRIVE"
sha256sum "$FINAL_APK_DRIVE"

if [ "$BUILD_MODE" = "release" ]; then
    echo "[cert] keytool -printcert:"
    keytool -printcert -jarfile "$FINAL_APK_WSL" | head -30
fi

echo "[done] $BUILD_MODE $BUILD_VERSION"
