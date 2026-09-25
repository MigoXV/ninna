FROM ninna/pytorch-runtime:v2
LABEL org.ninna.ecosystem="huggingface" org.ninna.runtime.version="v3"
ENV HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
WORKDIR /workspace
CMD ["python", "--version"]
