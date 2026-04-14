# Pharos Deployment Options Comparison

**Last Updated**: April 11, 2026

This document compares different deployment strategies for Pharos to help you choose the best option for your use case.

---

## Quick Comparison Table

| Feature | Serverless Stack | Native Render Stack | Self-Hosted | Local Dev |
|---------|------------------|---------------------|-------------|-----------|
| **Cost** | $7/mo | $24/mo | $0/mo (hardware) | $0/mo |
| **Setup Time** | 30 min | 30 min | 2-4 hours | 10 min |
| **Scalability** | Infinite | Limited | Manual | N/A |
| **Cold Starts** | None | None | None | N/A |
| **Maintenance** | Minimal | Minimal | High | None |
| **Best For** | Solo dev, small team | Teams, production | Privacy, control | Development |

---

## Detailed Comparison

### 1. Serverless Stack (Recommended)

**Architecture**: Render + NeonDB + Upstash + Local Edge Worker

#### Pros
- ✅ **Lowest cost**: $7/mo (71% savings vs native)
- ✅ **Infinite scalability**: Databases scale to zero
- ✅ **Zero cold starts**: API always-on
- ✅ **17x storage reduction**: Hybrid GitHub storage
- ✅ **Minimal maintenance**: Managed services
- ✅ **Production-ready**: Connection pooling, retries, timeouts
- ✅ **Fast deployment**: 30 minutes
- ✅ **Global edge**: Upstash Redis (<50ms latency)

#### Cons
- ⚠️ **Requires internet**: For GitHub API and serverless databases
- ⚠️ **Free tier limits**: NeonDB (500MB), Upstash (10K req/day)
- ⚠️ **Vendor lock-in**: Tied to Render, NeonDB, Upstash
- ⚠️ **Limited control**: Can't customize infrastructure

#### Cost Breakdown
| Service | Plan | Cost |
|---------|------|------|
| Render Web Service | Starter (512MB) | $7/mo |
| NeonDB PostgreSQL | Free (500MB) | $0/mo |
| Upstash Redis | Free (10K req/day) | $0/mo |
| Local Edge Worker | Your hardware | $0/mo |
| **TOTAL** | | **$7/mo** |

#### Capacity
- **Repos**: 100+ (with hybrid storage: 1000+)
- **Requests**: <100/min
- **Users**: 1-5
- **Storage**: 500MB (metadata + embeddings)

#### When to Choose
- Solo developer or small team
- Budget-conscious
- Want minimal maintenance
- Need fast deployment
- Don't need full control

---

### 2. Native Render Stack

**Architecture**: Render Web + Render PostgreSQL + Render Redis

#### Pros
- ✅ **Single vendor**: All services from Render
- ✅ **Easy setup**: One-click deployment
- ✅ **Integrated monitoring**: Unified dashboard
- ✅ **No external dependencies**: Self-contained
- ✅ **Predictable pricing**: Fixed monthly cost
- ✅ **Zero cold starts**: All services always-on

#### Cons
- ⚠️ **Higher cost**: $24/mo (3.4x more than serverless)
- ⚠️ **Limited scalability**: Fixed resources
- ⚠️ **No storage optimization**: Full code storage required
- ⚠️ **Vendor lock-in**: Tied to Render
- ⚠️ **Manual scaling**: Upgrade plans manually

#### Cost Breakdown
| Service | Plan | Cost |
|---------|------|------|
| Render Web Service | Starter (512MB) | $7/mo |
| Render PostgreSQL | Starter (1GB) | $7/mo |
| Render Redis | Starter (256MB) | $10/mo |
| **TOTAL** | | **$24/mo** |

#### Capacity
- **Repos**: 10-50 (full code storage)
- **Requests**: <100/min
- **Users**: 1-5
- **Storage**: 1GB (full code + metadata)

#### When to Choose
- Want single vendor simplicity
- Don't mind higher cost
- Need predictable pricing
- Want integrated monitoring
- Don't need hybrid storage

---

### 3. Self-Hosted

**Architecture**: Your server + PostgreSQL + Redis + Local Edge Worker

#### Pros
- ✅ **Full control**: Complete infrastructure control
- ✅ **Privacy**: Data stays on your hardware
- ✅ **No vendor lock-in**: Use any provider
- ✅ **Customizable**: Modify infrastructure as needed
- ✅ **No monthly cost**: One-time hardware investment
- ✅ **Unlimited capacity**: Scale hardware as needed

#### Cons
- ⚠️ **High maintenance**: Manual updates, backups, monitoring
- ⚠️ **Upfront cost**: Server hardware ($500-2000)
- ⚠️ **Complexity**: Requires DevOps expertise
- ⚠️ **No auto-scaling**: Manual capacity planning
- ⚠️ **Single point of failure**: No built-in redundancy
- ⚠️ **Slow deployment**: 2-4 hours setup

#### Cost Breakdown
| Item | Cost |
|------|------|
| Server hardware | $500-2000 (one-time) |
| Electricity | ~$10/mo |
| Internet | Existing |
| **TOTAL** | **~$10/mo** (after hardware) |

#### Capacity
- **Repos**: Unlimited (depends on hardware)
- **Requests**: Unlimited (depends on hardware)
- **Users**: Unlimited (depends on hardware)
- **Storage**: Unlimited (depends on hardware)

#### When to Choose
- Need full control
- Privacy is critical
- Have DevOps expertise
- Want to avoid vendor lock-in
- Have existing hardware

---

### 4. Local Development

**Architecture**: Local PostgreSQL + Local Redis + Local Edge Worker

#### Pros
- ✅ **Free**: No cost
- ✅ **Fast iteration**: Instant code changes
- ✅ **Offline**: No internet required
- ✅ **Full control**: Modify anything
- ✅ **Easy debugging**: Direct access to logs

#### Cons
- ⚠️ **Not production-ready**: No redundancy, backups
- ⚠️ **Single machine**: No scalability
- ⚠️ **Manual setup**: Install dependencies manually
- ⚠️ **No monitoring**: No built-in observability
- ⚠️ **Data loss risk**: No automatic backups

#### Cost Breakdown
| Item | Cost |
|------|------|
| Everything | $0/mo |

#### Capacity
- **Repos**: Limited by disk space
- **Requests**: Limited by CPU/RAM
- **Users**: 1 (you)
- **Storage**: Limited by disk space

#### When to Choose
- Development only
- Testing features
- Learning Pharos
- Offline work
- No budget

---

## Feature Comparison Matrix

| Feature | Serverless | Native Render | Self-Hosted | Local Dev |
|---------|------------|---------------|-------------|-----------|
| **Deployment** |
| Setup time | 30 min | 30 min | 2-4 hours | 10 min |
| Complexity | Low | Low | High | Medium |
| Automation | High | High | Manual | Manual |
| **Cost** |
| Monthly cost | $7 | $24 | ~$10 | $0 |
| Upfront cost | $0 | $0 | $500-2000 | $0 |
| Scaling cost | Pay-as-you-grow | Fixed tiers | Hardware | N/A |
| **Performance** |
| API latency | <200ms | <200ms | <100ms | <50ms |
| Cold starts | None | None | None | None |
| Global edge | Yes (Upstash) | No | No | No |
| **Scalability** |
| Auto-scaling | Yes | No | No | No |
| Max repos | 1000+ | 50 | Unlimited | Limited |
| Max requests/min | 100+ | 100+ | Unlimited | Limited |
| **Reliability** |
| Uptime SLA | 99.9% | 99.9% | Manual | N/A |
| Redundancy | Yes | Yes | Manual | No |
| Backups | Automatic | Automatic | Manual | Manual |
| **Maintenance** |
| Updates | Automatic | Automatic | Manual | Manual |
| Monitoring | Built-in | Built-in | Manual | Manual |
| Alerts | Built-in | Built-in | Manual | Manual |
| **Security** |
| SSL/TLS | Enforced | Enforced | Manual | Manual |
| Firewall | Built-in | Built-in | Manual | Manual |
| DDoS protection | Yes | Yes | Manual | No |
| **Privacy** |
| Data location | Cloud | Cloud | Your server | Your machine |
| Vendor access | Yes | Yes | No | No |
| Compliance | Vendor-dependent | Vendor-dependent | Full control | Full control |

---

## Migration Paths

### From Local Dev → Serverless Stack
1. Export local database: `pg_dump pharos > backup.sql`
2. Create NeonDB project and import: `psql $DATABASE_URL < backup.sql`
3. Create Upstash Redis
4. Deploy to Render with environment variables
5. Test endpoints
6. **Time**: 1 hour

### From Serverless Stack → Native Render Stack
1. Create Render PostgreSQL service
2. Migrate data: `pg_dump $NEONDB_URL | psql $RENDER_DB_URL`
3. Create Render Redis service
4. Update environment variables
5. Redeploy
6. **Time**: 30 minutes

### From Native Render Stack → Self-Hosted
1. Set up server (Ubuntu 22.04 recommended)
2. Install PostgreSQL, Redis, Docker
3. Export Render database: `pg_dump $RENDER_DB_URL > backup.sql`
4. Import to self-hosted: `psql pharos < backup.sql`
5. Configure firewall, SSL, backups
6. Deploy application
7. **Time**: 4-8 hours

### From Self-Hosted → Serverless Stack
1. Export self-hosted database: `pg_dump pharos > backup.sql`
2. Create NeonDB project and import
3. Create Upstash Redis
4. Deploy to Render
5. Test endpoints
6. Decommission self-hosted server
7. **Time**: 2 hours

---

## Scaling Scenarios

### Scenario 1: Solo Developer (10-100 repos)
**Recommended**: Serverless Stack ($7/mo)
- Cost-effective
- Minimal maintenance
- Sufficient capacity
- Easy to scale up

### Scenario 2: Small Team (100-500 repos)
**Recommended**: Serverless Stack ($7-25/mo)
- Upgrade to Render Standard (2GB RAM)
- Stay on NeonDB Free (500MB)
- Stay on Upstash Free (10K req/day)
- Total: $25/mo

### Scenario 3: Startup (500-1000 repos)
**Recommended**: Serverless Stack ($50/mo)
- Render Standard (2GB RAM): $25/mo
- NeonDB Pro (3GB): $19/mo
- Upstash Pro (1M req/mo): $10/mo
- Total: $54/mo

### Scenario 4: Scale-up (1000-5000 repos)
**Recommended**: Serverless Stack or Self-Hosted ($200/mo or $10/mo)
- **Serverless**: Render Pro + NeonDB Scale + Upstash Pro = $164/mo
- **Self-Hosted**: Dedicated server + electricity = ~$10/mo
- Choose based on: DevOps expertise, privacy needs, control requirements

### Scenario 5: Enterprise (5000+ repos)
**Recommended**: Self-Hosted or Hybrid
- Self-hosted for control and privacy
- Hybrid: Self-hosted database + Render API
- Custom infrastructure
- Dedicated DevOps team

---

## Decision Tree

```
Start here: What's your primary concern?

├─ Cost
│  ├─ Minimal cost → Serverless Stack ($7/mo)
│  ├─ No monthly cost → Self-Hosted (~$10/mo after hardware)
│  └─ Don't care → Native Render Stack ($24/mo)
│
├─ Privacy
│  ├─ Critical → Self-Hosted
│  ├─ Important → Self-Hosted
│  └─ Not important → Serverless Stack
│
├─ Maintenance
│  ├─ Minimal → Serverless Stack or Native Render Stack
│  ├─ Some → Serverless Stack
│  └─ Don't mind → Self-Hosted
│
├─ Scalability
│  ├─ Infinite → Serverless Stack
│  ├─ Predictable → Native Render Stack
│  └─ Unlimited → Self-Hosted
│
├─ Control
│  ├─ Full control → Self-Hosted
│  ├─ Some control → Serverless Stack
│  └─ Don't care → Native Render Stack
│
└─ Expertise
   ├─ DevOps expert → Self-Hosted
   ├─ Developer → Serverless Stack
   └─ Beginner → Native Render Stack
```

---

## Recommendations by Use Case

### For Solo Developers
**Best**: Serverless Stack ($7/mo)
- Lowest cost
- Minimal maintenance
- Sufficient capacity
- Easy to scale

### For Small Teams (2-5 people)
**Best**: Serverless Stack ($7-25/mo)
- Cost-effective
- Collaborative features
- Scales with team
- Minimal DevOps

### For Startups (5-20 people)
**Best**: Serverless Stack ($50/mo) or Self-Hosted
- Serverless: Easy scaling, minimal DevOps
- Self-Hosted: Full control, privacy
- Choose based on: Budget, expertise, privacy needs

### For Enterprises (20+ people)
**Best**: Self-Hosted or Hybrid
- Full control
- Privacy compliance
- Custom infrastructure
- Dedicated DevOps team

### For Privacy-Critical Use Cases
**Best**: Self-Hosted
- Data stays on your hardware
- No vendor access
- Full compliance control
- Custom security policies

### For Development/Testing
**Best**: Local Dev ($0/mo)
- Free
- Fast iteration
- Offline work
- Easy debugging

---

## Conclusion

**Most users should choose the Serverless Stack** because it offers:
- Lowest cost ($7/mo)
- Minimal maintenance
- Infinite scalability
- Production-ready
- Fast deployment (30 min)

**Choose Self-Hosted if**:
- Privacy is critical
- You have DevOps expertise
- You want full control
- You have existing hardware

**Choose Native Render Stack if**:
- You want single vendor simplicity
- You don't mind higher cost ($24/mo)
- You need predictable pricing

**Choose Local Dev if**:
- Development/testing only
- Learning Pharos
- No budget

---

**Questions?** Check the [Serverless Deployment Guide](SERVERLESS_DEPLOYMENT_GUIDE.md) for detailed instructions.
