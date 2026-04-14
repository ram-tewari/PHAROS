"""
Complete GPU Verification and Performance Test
Run this after reinstalling PyTorch with CUDA 12.1
"""
import time
import sys

print("="*70)
print("GPU VERIFICATION AND PERFORMANCE TEST")
print("="*70)
print()

# Step 1: Check PyTorch installation
print("STEP 1: Checking PyTorch Installation")
print("-"*70)
try:
    import torch
    print(f"✅ PyTorch version: {torch.__version__}")
    
    # Check if it's the right version
    if "cu121" in torch.__version__:
        print("✅ CUDA 12.1 version detected (correct for RTX 4070)")
    elif "cu118" in torch.__version__:
        print("❌ CUDA 11.8 version detected (TOO OLD for RTX 4070)")
        print()
        print("Please reinstall PyTorch with CUDA 12.1:")
        print("pip uninstall torch torchvision torchaudio")
        print("pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121")
        sys.exit(1)
    
    print(f"   Compiled with CUDA: {torch.version.cuda}")
    print()
except ImportError:
    print("❌ PyTorch not installed!")
    sys.exit(1)

# Step 2: Check GPU detection
print("STEP 2: GPU Detection")
print("-"*70)
cuda_available = torch.cuda.is_available()
print(f"CUDA available: {cuda_available}")

if cuda_available:
    print(f"✅ GPU detected!")
    print(f"   GPU count: {torch.cuda.device_count()}")
    print(f"   GPU name: {torch.cuda.get_device_name(0)}")
    
    # Check if it's RTX 4070
    gpu_name = torch.cuda.get_device_name(0)
    if "4070" in gpu_name:
        print(f"✅ RTX 4070 confirmed!")
    
    props = torch.cuda.get_device_properties(0)
    print(f"   Memory: {props.total_memory / 1024**3:.2f} GB")
    print(f"   Compute capability: {props.major}.{props.minor}")
    
    if props.major == 8 and props.minor == 9:
        print(f"✅ Compute capability 8.9 (Ada Lovelace - RTX 40 series)")
    
    print()
else:
    print("❌ No GPU detected!")
    print()
    print("Possible issues:")
    print("1. PyTorch version is still CUDA 11.8 (need CUDA 12.1)")
    print("2. NVIDIA drivers not installed")
    print("3. Need to restart Python/terminal after reinstall")
    print()
    sys.exit(1)

# Step 3: Test embedding generator
print("STEP 3: Testing Embedding Generator")
print("-"*70)
try:
    from app.shared.embeddings import EmbeddingGenerator
    
    gen = EmbeddingGenerator()
    print(f"Device detected by EmbeddingGenerator: {gen.device}")
    
    if gen.device == "cuda":
        print("✅ Embedding generator will use GPU!")
    else:
        print("❌ Embedding generator will use CPU (something wrong)")
        sys.exit(1)
    
    print()
except Exception as e:
    print(f"❌ Error loading EmbeddingGenerator: {e}")
    sys.exit(1)

# Step 4: Warmup test
print("STEP 4: Model Warmup (one-time cost)")
print("-"*70)
start = time.time()
warmup_success = gen.warmup()
warmup_time = (time.time() - start) * 1000

if warmup_success:
    print(f"✅ Warmup successful: {warmup_time:.2f}ms")
    if warmup_time < 2000:
        print(f"✅ EXCELLENT - Much faster than CPU (was 7,754ms)")
    else:
        print(f"⚠️  Slower than expected for GPU")
else:
    print("❌ Warmup failed!")
    sys.exit(1)

print()

# Step 5: Performance tests
print("STEP 5: GPU Performance Tests")
print("="*70)
print()

# Test 1: Short text
print("Test 1: Short text (38 chars)")
print("-"*70)
text1 = "This is a test of the embedding system"
start = time.time()
emb1 = gen.generate_embedding(text1)
time1 = (time.time() - start) * 1000

print(f"Time: {time1:.2f}ms")
print(f"Embedding dim: {len(emb1)}")
print(f"Success: {len(emb1) > 0}")

if time1 < 30:
    print(f"✅ EXCELLENT - GPU acceleration working! (CPU was 138ms)")
    speedup1 = 138 / time1
    print(f"   Speedup: {speedup1:.1f}x faster than CPU")
elif time1 < 100:
    print(f"✅ GOOD - Faster than CPU (was 138ms)")
else:
    print(f"⚠️  Slower than expected for GPU")

print()

# Test 2: Medium text
print("Test 2: Medium text (~1,346 chars)")
print("-"*70)
text2 = '''Machine learning is a subset of artificial intelligence that focuses on 
developing systems that can learn from data. Deep learning, a subset of 
machine learning, uses neural networks with multiple layers to process 
complex patterns in large datasets. These techniques have revolutionized 
fields like computer vision, natural language processing, and robotics.
Natural language processing enables computers to understand, interpret, and 
generate human language. Computer vision allows machines to interpret and 
understand visual information from the world. Robotics combines these 
technologies to create intelligent machines that can interact with their 
environment.''' * 2

start = time.time()
emb2 = gen.generate_embedding(text2)
time2 = (time.time() - start) * 1000

print(f"Text length: {len(text2)} chars")
print(f"Time: {time2:.2f}ms")
print(f"Embedding dim: {len(emb2)}")
print(f"Success: {len(emb2) > 0}")

if time2 < 150:
    print(f"✅ EXCELLENT - GPU acceleration working! (CPU was 814ms)")
    speedup2 = 814 / time2
    print(f"   Speedup: {speedup2:.1f}x faster than CPU")
elif time2 < 500:
    print(f"✅ GOOD - Faster than CPU (was 814ms)")
else:
    print(f"⚠️  Slower than expected for GPU")

print()

# Test 3: Typical document
print("Test 3: Typical document (~13,460 chars, 1000 words)")
print("-"*70)
text_1000 = text2 * 10

start = time.time()
emb_1000 = gen.generate_embedding(text_1000)
time3 = (time.time() - start) * 1000

print(f"Text length: {len(text_1000)} chars")
print(f"Time: {time3:.2f}ms")
print(f"Embedding dim: {len(emb_1000)}")
print(f"Success: {len(emb_1000) > 0}")

if time3 < 300:
    print(f"✅ EXCELLENT - GPU acceleration working! (CPU was 1,637ms)")
    speedup3 = 1637 / time3
    print(f"   Speedup: {speedup3:.1f}x faster than CPU")
elif time3 < 1000:
    print(f"✅ GOOD - Faster than CPU (was 1,637ms)")
else:
    print(f"⚠️  Slower than expected for GPU")

print()

# Test 4: Batch processing
print("Test 4: Batch processing (100 documents)")
print("-"*70)
texts100 = [f'Document {i}: Machine learning and AI are transforming technology.' for i in range(100)]

start = time.time()
embs100 = [gen.generate_embedding(t) for t in texts100]
time4 = (time.time() - start) * 1000

print(f"Total time: {time4:.2f}ms")
print(f"Per document: {time4/100:.2f}ms")
print(f"All embeddings generated: {len(embs100) == 100 and all(len(e) > 0 for e in embs100)}")

if time4/100 < 15:
    print(f"✅ EXCELLENT - GPU batch processing working! (CPU was 59ms/doc)")
    speedup4 = 59 / (time4/100)
    print(f"   Speedup: {speedup4:.1f}x faster than CPU")
elif time4/100 < 40:
    print(f"✅ GOOD - Faster than CPU (was 59ms/doc)")
else:
    print(f"⚠️  Slower than expected for GPU")

print()

# Summary
print("="*70)
print("PERFORMANCE SUMMARY")
print("="*70)
print()

print(f"Device: {gen.device}")
print(f"GPU: {torch.cuda.get_device_name(0)}")
print(f"Model: {gen.model_name}")
print()

print("Performance Results:")
print(f"  Warmup: {warmup_time:.2f}ms (CPU: 7,754ms)")
print(f"  Short text: {time1:.2f}ms (CPU: 138ms) - {138/time1:.1f}x faster")
print(f"  Medium text: {time2:.2f}ms (CPU: 814ms) - {814/time2:.1f}x faster")
print(f"  Typical doc: {time3:.2f}ms (CPU: 1,637ms) - {1637/time3:.1f}x faster")
print(f"  Batch 100: {time4/100:.2f}ms per doc (CPU: 59ms) - {59/(time4/100):.1f}x faster")
print()

# Calculate average speedup
avg_speedup = (138/time1 + 814/time2 + 1637/time3 + 59/(time4/100)) / 4
print(f"Average speedup: {avg_speedup:.1f}x faster than CPU")
print()

# Verdict
if avg_speedup > 6:
    print("✅ VERDICT: GPU ACCELERATION WORKING PERFECTLY!")
    print("   Your RTX 4070 is delivering excellent performance.")
elif avg_speedup > 3:
    print("✅ VERDICT: GPU ACCELERATION WORKING!")
    print("   Performance is good but could be better.")
else:
    print("⚠️  VERDICT: GPU NOT PERFORMING AS EXPECTED")
    print("   Check if GPU is under load or thermal throttling.")

print()
print("="*70)
print("TEST COMPLETE")
print("="*70)
