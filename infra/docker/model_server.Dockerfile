# Model Server Dockerfile — containerises the llama-cpp-python inference server
# Note 1: Arthvidya (the local LLM) runs via llama-cpp-python, a Python binding
# for llama.cpp — a C++ inference engine optimised for running quantised LLM
# models (GGUF format) efficiently on CPU and GPU. It exposes an OpenAI-compatible
# REST API that LLMClient (backend/core/llm_client.py) calls for every chat turn.
#
# Note 2: Model server containers require special hardware configuration:
# - For GPU inference: '--gpus all' flag in docker run (or 'deploy: resources: reservations: devices' in docker-compose)
# - For CPU inference: no special flags, but more RAM is needed (typically 8-16GB for a 7B model)
# - The GGUF model file must be mounted into the container (not baked into the image — it is too large)
#
# Note 3: Typical Dockerfile:
#
# FROM python:3.12-slim
# RUN pip install llama-cpp-python[server] --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
# EXPOSE 8080
# # The model file is expected at /models/arthvidya.gguf (mounted at runtime)
# CMD ["python", "-m", "llama_cpp.server", \
#      "--model", "/models/arthvidya.gguf", \
#      "--host", "0.0.0.0", \
#      "--port", "8080", \
#      "--n_gpu_layers", "0"]    # 0 = CPU only; set to 35+ for GPU
#
# Note 4: n_gpu_layers controls how many transformer layers are offloaded to GPU.
# 0 = pure CPU, -1 = all layers on GPU. Partial offload (e.g. 20 layers) is useful
# when the model is too large to fit entirely in VRAM.
#
# TODO: Add llama-cpp-python server containerization steps
