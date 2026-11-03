# Shared settings for every second-brain script that calls qmd. Source it, don't run it.
# qmd picks the best way to run its models on your computer. To force one, set QMD_LLAMA_GPU before you run a
# script (for example QMD_LLAMA_GPU=false to use the processor only, or vulkan / cuda for a graphics card).
# One model context for searches: faster to start when the computer is busy.
export QMD_EMBED_PARALLELISM="${QMD_EMBED_PARALLELISM:-1}"
# qmd is usually a global npm package; these folders hold npm and pip installs and are not always on PATH under systemd.
export PATH="$HOME/.local/bin:$HOME/.local/share/mise/shims:$PATH"
