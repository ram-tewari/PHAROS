"""Check GPU availability"""
import torch

print(f'PyTorch installed: {torch.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
print(f'CUDA version: {torch.version.cuda if torch.cuda.is_available() else "N/A"}')
print(f'GPU count: {torch.cuda.device_count() if torch.cuda.is_available() else 0}')
if torch.cuda.is_available():
    print(f'GPU name: {torch.cuda.get_device_name(0)}')
else:
    print('GPU name: N/A')
