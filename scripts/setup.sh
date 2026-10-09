#!/bin/sh
set -eu
PROJECT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ROOT=$(dirname "$PROJECT")
command -v uv >/dev/null || { echo '需要先安装 uv：https://docs.astral.sh/uv/'; exit 1; }
command -v npm >/dev/null || { echo '需要 Node.js 和 npm。'; exit 1; }
mkdir -p "$ROOT/vendor"
[ -d "$ROOT/vendor/microduck" ] || {
    git clone https://github.com/pollen-robotics/microduck.git "$ROOT/vendor/microduck"
    git -C "$ROOT/vendor/microduck" checkout --detach 1fa84386f07884e27866411bc1ba166977bced95
}
[ -d "$ROOT/vendor/microduck_rl" ] || {
    git clone https://github.com/pollen-robotics/microduck_rl.git "$ROOT/vendor/microduck_rl"
    git -C "$ROOT/vendor/microduck_rl" checkout --detach 8d0db74916a4f833d1d9b95d6a1d7f4d13b9d5ec
}
[ -d "$ROOT/vendor/bam" ] || {
    git clone https://github.com/Rhoban/bam.git "$ROOT/vendor/bam"
    git -C "$ROOT/vendor/bam" checkout --detach 62bd8ce12154340be97e06f7f41a0ca8f116d967
}
# Known compatible snapshots. Never reset an existing checkout or discard local work.
git -C "$ROOT/vendor/microduck" rev-parse HEAD
git -C "$ROOT/vendor/microduck_rl" rev-parse HEAD
git -C "$ROOT/vendor/bam" rev-parse HEAD
[ -x "$PROJECT/.venv/bin/python" ] || uv venv --python 3.12 "$PROJECT/.venv"
uv pip install --python "$PROJECT/.venv/bin/python" -r "$PROJECT/requirements.txt"
uv pip install --python "$PROJECT/.venv/bin/python" "$ROOT/vendor/bam[mujoco]"
if [ -x "$ROOT/.runtime/cargo/bin/cargo" ]; then
    export CARGO_HOME="$ROOT/.runtime/cargo"
    export RUSTUP_HOME="$ROOT/.runtime/rustup"
    export PATH="$CARGO_HOME/bin:$PATH"
fi
command -v cargo >/dev/null || { echo '需要 Rust 1.99 或更新版本：https://rustup.rs/'; exit 1; }
cargo build --manifest-path "$ROOT/vendor/microduck/Cargo.toml" -p robotd -p robotctl
sh "$ROOT/vendor/microduck/scripts/seed-policies.sh" "$PROJECT/data/policies"
(cd "$PROJECT/web" && npm ci)
echo '准备完成。运行 python3 scripts/dev.py 启动本地实验室。'
