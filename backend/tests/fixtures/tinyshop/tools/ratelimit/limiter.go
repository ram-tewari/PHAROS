// Package ratelimit throttles API clients with a token bucket.
package ratelimit

import (
	"sync"
	"time"
)

// Bucket is a token-bucket rate limiter.
type Bucket struct {
	mu       sync.Mutex
	capacity float64
	tokens   float64
	rate     float64
	last     time.Time
}

// NewBucket creates a bucket that refills `rate` tokens per second.
func NewBucket(capacity, rate float64) *Bucket {
	return &Bucket{capacity: capacity, tokens: capacity, rate: rate, last: time.Now()}
}

// Allow reports whether one request may proceed, consuming a token if so.
func (b *Bucket) Allow() bool {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.refill(time.Now())
	if b.tokens < 1 {
		return false
	}
	b.tokens--
	return true
}

// refill adds tokens for the time elapsed since the last call.
func (b *Bucket) refill(now time.Time) {
	elapsed := now.Sub(b.last).Seconds()
	b.tokens = min(b.capacity, b.tokens+elapsed*b.rate)
	b.last = now
}
