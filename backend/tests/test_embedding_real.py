"""
Real Embedding Performance Test
Tests actual performance with fixes applied
"""
from app.shared.embeddings import EmbeddingGenerator
import time

print('Testing Embedding Generation with Fixes...')
print('='*60)

# Initialize generator
gen = EmbeddingGenerator()
print(f'Device detected: {gen.device}')
print()

# Test warmup
print('Testing warmup...')
start = time.time()
warmup_success = gen.warmup()
warmup_time = (time.time() - start) * 1000
print(f'Warmup: {"SUCCESS" if warmup_success else "FAILED"} ({warmup_time:.2f}ms)')
print()

# Test single short text
print('Test 1: Short text (38 chars)')
text1 = 'This is a test of the embedding system'
start = time.time()
emb1 = gen.generate_embedding(text1)
time1 = (time.time() - start) * 1000
print(f'Time: {time1:.2f}ms')
print(f'Embedding dim: {len(emb1)}')
print(f'Success: {len(emb1) > 0}')
print()

# Test single medium text
print('Test 2: Medium text (~200 words)')
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
print(f'Text length: {len(text2)} chars')
print(f'Time: {time2:.2f}ms')
print(f'Embedding dim: {len(emb2)}')
print(f'Success: {len(emb2) > 0}')
print()

# Test multiple documents (simulated batch)
print('Test 3: Multiple documents (10 docs, sequential)')
texts = [f'This is test document number {i} with some content about machine learning and AI.' for i in range(10)]
start = time.time()
embs = [gen.generate_embedding(t) for t in texts]
time3 = (time.time() - start) * 1000
print(f'Total time: {time3:.2f}ms')
print(f'Per document: {time3/10:.2f}ms')
print(f'All embeddings generated: {len(embs) == 10 and all(len(e) > 0 for e in embs)}')
print()

# Test more documents
print('Test 4: Multiple documents (100 docs, sequential)')
texts100 = [f'Document {i}: Machine learning and artificial intelligence are transforming technology.' for i in range(100)]
start = time.time()
embs100 = [gen.generate_embedding(t) for t in texts100]
time4 = (time.time() - start) * 1000
print(f'Total time: {time4:.2f}ms')
print(f'Per document: {time4/100:.2f}ms')
print(f'All embeddings generated: {len(embs100) == 100 and all(len(e) > 0 for e in embs100)}')
print()

# Test typical document (1000 words)
print('Test 5: Typical document (~1000 words)')
text_1000 = text2 * 10  # Approximately 1000 words
start = time.time()
emb_1000 = gen.generate_embedding(text_1000)
time5 = (time.time() - start) * 1000
print(f'Text length: {len(text_1000)} chars')
print(f'Time: {time5:.2f}ms')
print(f'Embedding dim: {len(emb_1000)}')
print(f'Success: {len(emb_1000) > 0}')
print()

# Summary
print('='*60)
print('SUMMARY')
print('='*60)
print(f'Device: {gen.device}')
print(f'Model loaded: {gen._model is not None}')
print(f'Warmed up: {gen._warmed_up}')
print()
print('Performance Results:')
print(f'  Short text (38 chars): {time1:.2f}ms')
print(f'  Medium text (~500 chars): {time2:.2f}ms')
print(f'  Typical doc (~5000 chars): {time5:.2f}ms')
print(f'  Batch 10 docs: {time3:.2f}ms ({time3/10:.2f}ms per doc)')
print(f'  Batch 100 docs: {time4:.2f}ms ({time4/100:.2f}ms per doc)')
print()
print('Note: Batch processing uses sequential encoding (not true batching)')
print('      True batching would be 6-7x faster with model.encode()')
print()
print('Comparison to Claims:')
print(f'  Claimed: <2000ms per document')
print(f'  Actual (typical doc): {time5:.2f}ms')
if time5 > 0:
    print(f'  Result: {2000/time5:.1f}x FASTER than claimed')
else:
    print(f'  Result: MUCH faster than claimed')
print()

# Determine verdict
if gen.device == 'cuda':
    expected_time = 10  # 10ms on GPU
    device_type = 'GPU'
else:
    expected_time = 30  # 30ms on CPU
    device_type = 'CPU'

if time5 < expected_time:
    verdict = f'✅ EXCELLENT - Faster than expected for {device_type}'
elif time5 < 100:
    verdict = f'✅ GOOD - Within expected range for {device_type}'
elif time5 < 2000:
    verdict = f'✅ ACCEPTABLE - Meets claimed performance'
else:
    verdict = f'❌ SLOW - Does not meet claimed performance'

print(f'Verdict: {verdict}')
