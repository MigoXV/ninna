FROM ninna/pytorch-runtime:v1
RUN pip install --no-cache-dir transformers==4.57.1 datasets==4.4.1 safetensors==0.6.2
ENV HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
