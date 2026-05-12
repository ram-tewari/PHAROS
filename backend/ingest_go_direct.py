#!/usr/bin/env python3
"""
Direct ingestion script for Go repositories (bypasses worker queue).

This script uses HybridIngestionPipeline directly to ingest a Go repository
and test Phase 2 polyglot AST support.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from app.modules.ingestion.ast_pipeline import HybridIngestionPipeline
from app.shared.database import get_sync_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

logger = logging.getLogger(__name__)


async def ingest_go_repo(repo_url: str):
    """Ingest a Go repository directly."""
    logger.info(f"Starting ingestion of {repo_url}")
    
    # Initialize database
    from app.shared.database import init_database, get_db
    init_database()
    
    # Get async database session
    async for db in get_db():
        try:
            # Create pipeline
            pipeline = HybridIngestionPipeline(db)
            
            # Run ingestion
            logger.info("Running ingestion pipeline...")
            result = await pipeline.ingest_github_repo(repo_url)
            
            logger.info("=" * 80)
            logger.info("INGESTION COMPLETE")
            logger.info("=" * 80)
            logger.info(f"Repository: {result.repo_url}")
            logger.info(f"Branch: {result.branch}")
            logger.info(f"Commit SHA: {result.commit_sha}")
            logger.info(f"Resources created: {result.resources_created}")
            logger.info(f"Chunks created: {result.chunks_created}")
            logger.info(f"Files skipped: {result.files_skipped}")
            logger.info(f"Files failed: {result.files_failed}")
            logger.info(f"Storage saved: {result.storage_saved_mb:.2f} MB")
            logger.info(f"Duration: {result.ingestion_time_seconds:.2f}s")
            
            if result.errors:
                logger.warning(f"Errors encountered: {len(result.errors)}")
                for error in result.errors[:5]:  # Show first 5 errors
                    logger.warning(f"  - {error}")
            
            return result
            
        except Exception as e:
            logger.error(f"Ingestion failed: {e}", exc_info=True)
            raise


if __name__ == "__main__":
    # Test with a small Go repository
    repo_url = "https://github.com/fatih/color"
    
    logger.info("=" * 80)
    logger.info("DIRECT GO REPOSITORY INGESTION")
    logger.info(f"Repository: {repo_url}")
    logger.info("=" * 80)
    
    try:
        result = asyncio.run(ingest_go_repo(repo_url))
        
        logger.info("\n" + "=" * 80)
        logger.info("SUCCESS: Go repository ingested")
        logger.info("=" * 80)
        logger.info("\nNext: Search for Go code to verify AST extraction")
        logger.info("  Query: 'color' or 'Print'")
        logger.info("  Expected: ast_node_type='function', not 'block'")
        
        sys.exit(0)
        
    except Exception as e:
        logger.error(f"\nFAILED: {e}")
        sys.exit(1)
