# Shared settings for every second-brain script that calls qmd. Source it, don't run it.
# qmd's models run on the graphics card through Vulkan. On the processor, searches stalled for
# minutes (or failed) whenever the computer was busy, because llama.cpp's threads fight other
# work for the cores. qmd's prebuilt CUDA build crashes on this GTX 1060 (Pascal: "no kernel image
# is available"), so never use QMD_LLAMA_GPU=cuda. QMD_LLAMA_GPU=false forces the processor.
# qmd frees the models (and the card's memory) after 5 idle minutes.
export QMD_LLAMA_GPU="${QMD_LLAMA_GPU:-vulkan}"
# One model context for searches: faster to start when the computer is busy.
export QMD_EMBED_PARALLELISM="${QMD_EMBED_PARALLELISM:-1}"
# qmd is a global npm package in mise's node; the mise shim finds it from systemd too.
export PATH="$HOME/.local/share/mise/shims:$HOME/.local/bin:$PATH"
