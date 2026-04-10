"""Detailed GPU diagnostics"""
import sys
import os

print("="*60)
print("DETAILED GPU DIAGNOSTICS")
print("="*60)
print()

# Check Python version
print(f"Python version: {sys.version}")
print(f"Python executable: {sys.executable}")
print()

# Check PyTorch installation
try:
    import torch
    print(f"✅ PyTorch installed: {torch.__version__}")
    print(f"   PyTorch path: {torch.__file__}")
    print()
    
    # Check CUDA availability
    print(f"CUDA available: {torch.cuda.is_available()}")
    print(f"CUDA version (compiled): {torch.version.cuda}")
    print(f"cuDNN version: {torch.backends.cudnn.version() if torch.cuda.is_available() else 'N/A'}")
    print()
    
    # Check GPU details
    if torch.cuda.is_available():
        print(f"✅ GPU count: {torch.cuda.device_count()}")
        for i in range(torch.cuda.device_count()):
            print(f"   GPU {i}: {torch.cuda.get_device_name(i)}")
            print(f"   Memory: {torch.cuda.get_device_properties(i).total_memory / 1024**3:.2f} GB")
        print()
    else:
        print("❌ No GPU detected by PyTorch")
        print()
        
        # Try to diagnose why
        print("Diagnostic checks:")
        
        # Check if CUDA DLLs are accessible
        try:
            torch.cuda.init()
            print("   ✅ CUDA initialization succeeded")
        except Exception as e:
            print(f"   ❌ CUDA initialization failed: {e}")
        
        # Check environment variables
        print()
        print("Environment variables:")
        cuda_vars = ['CUDA_PATH', 'CUDA_HOME', 'CUDA_VISIBLE_DEVICES']
        for var in cuda_vars:
            val = os.environ.get(var, 'Not set')
            print(f"   {var}: {val}")
        
        print()
        print("Possible issues:")
        print("   1. PyTorch CPU-only version installed")
        print("   2. CUDA runtime libraries not found")
        print("   3. NVIDIA drivers not properly installed")
        print("   4. GPU in TCC mode (not WDDM)")
        print("   5. Antivirus blocking CUDA access")
        
except ImportError as e:
    print(f"❌ PyTorch not installed: {e}")
    print()

# Check sentence-transformers
try:
    import sentence_transformers
    print(f"✅ sentence-transformers installed: {sentence_transformers.__version__}")
except ImportError:
    print("❌ sentence-transformers not installed")

print()
print("="*60)
print("RECOMMENDATION")
print("="*60)

try:
    import torch
    if not torch.cuda.is_available():
        print()
        print("Your PyTorch installation cannot see the GPU.")
        print()
        print("To fix this, reinstall PyTorch with CUDA support:")
        print()
        print("1. Uninstall current PyTorch:")
        print("   pip uninstall torch torchvision torchaudio")
        print()
        print("2. Install PyTorch with CUDA 12.1 (for RTX 4070):")
        print("   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121")
        print()
        print("3. Verify installation:")
        print("   python backend/check_gpu.py")
        print()
except:
    pass
