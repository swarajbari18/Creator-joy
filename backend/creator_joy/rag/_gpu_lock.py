import threading

# Shared across embedder and reranker so concurrent sub-agent threads
# queue up rather than racing for GPU VRAM.
gpu_inference_lock = threading.Lock()
