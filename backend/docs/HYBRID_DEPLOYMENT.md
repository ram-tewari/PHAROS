# Hybrid Deployment Guide

To locally host Pharos without it becoming too "heavy" (e.g., avoiding massive local GPU requirements and model downloads), you can leverage the **Hybrid Edge-Cloud** mode.

## Architecture Modes
Pharos runs in two distinct modes:

1. **CLOUD Mode (Lightweight)**
   - **Characteristics:** Fast, lightweight API server. No Torch, no GPU required locally.
   - **Infrastructure:** Offloads heavy lifting to cloud providers (e.g., Upstash Redis, NeonDB, Qdrant Cloud).
   - **Use Case:** Best when running locally on weaker hardware (e.g. standard laptops) where you only need the API interface to communicate with a remote knowledge base or when using cloud LLM embeddings.

2. **EDGE Mode (Heavyweight)**
   - **Characteristics:** Full ML stack running locally with CUDA/MPS support.
   - **Infrastructure:** Local embeddings (nomic-embed-text), local repository parsing, local recommendation engine.
   - **Use Case:** Best for dedicated GPU servers or local workstations with high VRAM, prioritizing absolute privacy over memory constraints.

## How to Set Up the Lightweight Mode
Set your environment variables in `config/.env` to configure the lightweight cloud mode. Ensure you are directing components like the vector store and database to external services:
- `DATABASE_URL=postgresql://<user>:<password>@<neon_host>/<db>`
- `VECTOR_DB_URL=https://<qdrant_cloud_host>`
- `REDIS_URL=rediss://<upstash_host>`

When running `CLOUD` mode, your local Pharos instance primarily acts as an intelligent router and query engine (using the `Three-Way Hybrid Search`), without dragging down local system performance with embedding generation.
