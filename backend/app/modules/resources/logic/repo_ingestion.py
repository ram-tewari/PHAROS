"""Repository ingestion service for code intelligence pipeline."""

from pathlib import Path
from typing import List, Optional, Dict, Any
import logging
import tempfile
import shutil

from sqlalchemy.ext.asyncio import AsyncSession
import pathspec
import git

from app.database.models import Resource
from app.modules.resources.logic.classification import classify_file
from app.utils.path_exclusions import has_excluded_ancestor, is_excluded_file


logger = logging.getLogger(__name__)


# Global cache for .gitignore patterns (keyed by repo root path)
_GITIGNORE_CACHE: Dict[str, Optional[pathspec.PathSpec]] = {}


class RepoIngestionService:
    """Service for ingesting code repositories into Neo Alexandria."""

    def __init__(self, db: AsyncSession):
        """
        Initialize the repository ingestion service.

        Args:
            db: Async database session
        """
        self.db = db

    async def crawl_directory(
        self, root_path: Path, track_errors: bool = True, batch_size: int = 50
    ) -> tuple[List[Resource], Dict[str, Any]]:
        """
        Recursively crawl directory and create Resources.
        Respects .gitignore rules and filters binary files.
        Processes files in batches with transaction management.

        Args:
            root_path: Root directory to crawl
            track_errors: Whether to track failed files in metadata
            batch_size: Number of files to process per batch (default: 50)

        Returns:
            Tuple of (List of created Resource objects, Error metadata dict)

        Raises:
            ValueError: If root_path does not exist or is not a directory
        """
        if not root_path.exists():
            raise ValueError(f"Path does not exist: {root_path}")

        if not root_path.is_dir():
            raise ValueError(f"Path is not a directory: {root_path}")

        logger.info(f"Starting directory crawl: {root_path} (batch_size={batch_size})")

        # Load .gitignore patterns
        gitignore_spec = self._load_gitignore(root_path)

        # Discover all files using generator to avoid loading all into memory
        all_resources = []
        file_count = 0
        skipped_count = 0
        failed_files = []  # Track failed files

        # Use generator for memory-efficient directory traversal
        def discover_files():
            """Generator that yields files to process."""
            nonlocal file_count, skipped_count
            for file_path in root_path.rglob("*"):
                # Skip directories
                if file_path.is_dir():
                    continue

                file_count += 1

                # Skip .gitignore file itself
                if file_path.name == ".gitignore":
                    skipped_count += 1
                    logger.debug(f"Skipping .gitignore file: {file_path}")
                    continue

                # Check if file should be ignored
                if self.should_ignore_file(file_path, root_path, gitignore_spec):
                    skipped_count += 1
                    logger.debug(f"Skipping ignored file: {file_path}")
                    continue

                # Check if file is binary
                if self._is_binary_file(file_path):
                    skipped_count += 1
                    logger.debug(f"Skipping binary file: {file_path}")
                    continue

                yield file_path

        # Collect files in batches using generator
        files_to_process = list(discover_files())

        # Process files in batches
        total_batches = (len(files_to_process) + batch_size - 1) // batch_size
        logger.info(
            f"Processing {len(files_to_process)} files in {total_batches} batches"
        )

        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, len(files_to_process))
            batch_files = files_to_process[start_idx:end_idx]

            logger.debug(
                f"Processing batch {batch_num + 1}/{total_batches} ({len(batch_files)} files)"
            )

            # Process batch with transaction management
            batch_resources = []
            try:
                for file_path in batch_files:
                    # Create Resource with error handling
                    try:
                        resource = await self._create_resource_from_file(
                            file_path=file_path, root_path=root_path
                        )
                        batch_resources.append(resource)
                    except Exception as e:
                        error_msg = f"Failed to create resource for {file_path}: {e}"
                        logger.error(error_msg, exc_info=True)

                        # Track failed file if requested
                        if track_errors:
                            relative_path = str(file_path.relative_to(root_path))
                            failed_files.append(
                                {
                                    "path": relative_path,
                                    "error": str(e),
                                    "error_type": type(e).__name__,
                                }
                            )

                        # Continue processing other files in batch
                        continue

                # Commit batch transaction
                try:
                    await self.db.commit()
                    all_resources.extend(batch_resources)
                    logger.debug(
                        f"Batch {batch_num + 1}/{total_batches} committed: "
                        f"{len(batch_resources)} resources created"
                    )
                except Exception as e:
                    # Rollback on database error
                    logger.error(
                        f"Database error in batch {batch_num + 1}, rolling back: {e}",
                        exc_info=True,
                    )
                    await self.db.rollback()

                    # Track all files in this batch as failed
                    if track_errors:
                        for file_path in batch_files:
                            relative_path = str(file_path.relative_to(root_path))
                            # Only add if not already tracked
                            if not any(
                                f["path"] == relative_path for f in failed_files
                            ):
                                failed_files.append(
                                    {
                                        "path": relative_path,
                                        "error": f"Database transaction failed: {e}",
                                        "error_type": "DatabaseError",
                                    }
                                )

                    # Continue with next batch
                    continue

            except Exception as e:
                # Unexpected error in batch processing
                logger.error(
                    f"Unexpected error in batch {batch_num + 1}: {e}", exc_info=True
                )
                await self.db.rollback()

                # Track all files in this batch as failed
                if track_errors:
                    for file_path in batch_files:
                        relative_path = str(file_path.relative_to(root_path))
                        if not any(f["path"] == relative_path for f in failed_files):
                            failed_files.append(
                                {
                                    "path": relative_path,
                                    "error": f"Batch processing failed: {e}",
                                    "error_type": type(e).__name__,
                                }
                            )

                # Continue with next batch
                continue

        # Build error metadata
        error_metadata = {
            "total_files": file_count,
            "successful": len(all_resources),
            "skipped": skipped_count,
            "failed": len(failed_files),
            "failed_files": failed_files,
            "batches_processed": total_batches,
        }

        logger.info(
            f"Directory crawl complete: {len(all_resources)} resources created, "
            f"{skipped_count} files skipped, {len(failed_files)} files failed "
            f"out of {file_count} total files ({total_batches} batches)"
        )

        return all_resources, error_metadata

    async def clone_and_ingest(
        self, git_url: str, track_errors: bool = True, batch_size: int = 50
    ) -> tuple[List[Resource], Dict[str, Any]]:
        """
        Clone Git repository and ingest contents.

        Args:
            git_url: Git repository URL (https only)
            track_errors: Whether to track failed files in metadata
            batch_size: Number of files to process per batch (default: 50)

        Returns:
            Tuple of (List of created Resource objects, Error metadata dict)

        Raises:
            ValueError: If git_url is invalid or clone fails
        """
        # Validate URL
        if not git_url.startswith("https://"):
            raise ValueError("Only HTTPS URLs are supported for security reasons")

        logger.info(f"Cloning repository: {git_url}")

        # Create temporary directory with restricted permissions
        temp_dir = tempfile.mkdtemp(prefix="neo_alexandria_repo_")
        temp_path = Path(temp_dir)

        try:
            # Clone repository
            try:
                repo = git.Repo.clone_from(
                    git_url,
                    temp_path,
                    depth=1,  # Shallow clone for efficiency
                    # timeout parameter removed for Git < 2.47 compatibility
                )
            except git.GitCommandError as e:
                raise ValueError(f"Failed to clone repository: {e}")

            # Extract Git metadata
            commit_hash = repo.head.commit.hexsha
            branch = repo.active_branch.name if not repo.head.is_detached else "HEAD"

            logger.info(f"Repository cloned: commit={commit_hash}, branch={branch}")

            # Crawl the cloned repository with batch processing
            resources, error_metadata = await self.crawl_directory(
                temp_path, track_errors=track_errors, batch_size=batch_size
            )

            # Add Git metadata to all resources using relation field
            # Format: "git:commit_hash", "git:branch", "git:url"
            for resource in resources:
                git_relations = [
                    f"git:commit:{commit_hash}",
                    f"git:branch:{branch}",
                    f"git:url:{git_url}",
                ]
                # Append to existing relations
                if resource.relation:
                    resource.relation.extend(git_relations)
                else:
                    resource.relation = git_relations

            # Commit final changes to database
            await self.db.commit()

            logger.info(
                f"Repository ingestion complete: {len(resources)} resources created"
            )

            return resources, error_metadata

        finally:
            # Clean up temporary directory
            try:
                shutil.rmtree(temp_path)
                logger.debug(f"Cleaned up temporary directory: {temp_path}")
            except Exception as e:
                logger.warning(
                    f"Failed to clean up temporary directory {temp_path}: {e}"
                )

    def should_ignore_file(
        self,
        file_path: Path,
        root_path: Path,
        gitignore_spec: Optional[pathspec.PathSpec],
    ) -> bool:
        """
        Check if file should be ignored based on .gitignore rules.

        Args:
            file_path: Path to the file
            root_path: Root directory of the repository
            gitignore_spec: Compiled .gitignore patterns

        Returns:
            True if file should be ignored
        """
        try:
            relative_path = file_path.relative_to(root_path)
        except ValueError:
            return True

        if has_excluded_ancestor(relative_path.parts):
            return True

        if is_excluded_file(file_path.name):
            return True

        if gitignore_spec is None:
            return False

        relative_path_str = str(relative_path).replace("\\", "/")
        return gitignore_spec.match_file(relative_path_str)

    def _load_gitignore(self, root_path: Path) -> Optional[pathspec.PathSpec]:
        """
        Load and compile .gitignore patterns from repository.
        Uses cache to avoid reloading for the same repository.

        Args:
            root_path: Root directory of the repository

        Returns:
            Compiled PathSpec object or None if no .gitignore found
        """
        # Check cache first
        cache_key = str(root_path)
        if cache_key in _GITIGNORE_CACHE:
            logger.debug(f"Using cached .gitignore patterns for {root_path}")
            return _GITIGNORE_CACHE[cache_key]

        gitignore_path = root_path / ".gitignore"

        if not gitignore_path.exists():
            logger.debug("No .gitignore found")
            _GITIGNORE_CACHE[cache_key] = None
            return None

        try:
            with open(gitignore_path, "r", encoding="utf-8") as f:
                patterns = f.read().splitlines()

            # Filter out comments and empty lines
            patterns = [
                line.strip()
                for line in patterns
                if line.strip() and not line.strip().startswith("#")
            ]

            # Compile patterns
            spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns)
            logger.debug(f"Loaded {len(patterns)} .gitignore patterns")

            # Cache the compiled patterns
            _GITIGNORE_CACHE[cache_key] = spec
            return spec

        except Exception as e:
            logger.warning(f"Failed to load .gitignore: {e}")
            _GITIGNORE_CACHE[cache_key] = None
            return None

    def _is_binary_file(self, file_path: Path) -> bool:
        """
        Check if file is binary by looking for null bytes.

        Args:
            file_path: Path to the file

        Returns:
            True if file appears to be binary
        """
        try:
            # Read first 8KB to check for null bytes
            with open(file_path, "rb") as f:
                chunk = f.read(8192)
                return b"\x00" in chunk
        except Exception as e:
            logger.warning(f"Failed to check if file is binary {file_path}: {e}")
            # If we can't read it, assume it's binary
            return True

    async def _create_resource_from_file(
        self, file_path: Path, root_path: Path
    ) -> Resource:
        """
        Create a Resource from a file.

        Args:
            file_path: Path to the file
            root_path: Root directory of the repository

        Returns:
            Created Resource object with file metadata stored in Dublin Core fields
        """
        # Read file content
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            # Try with latin-1 encoding as fallback
            try:
                with open(file_path, "r", encoding="latin-1") as f:
                    content = f.read()
            except Exception as e:
                raise ValueError(f"Failed to read file {file_path}: {e}")

        # Get relative path
        relative_path = file_path.relative_to(root_path)
        relative_path_str = str(relative_path).replace("\\", "/")

        # Classify file
        classification = classify_file(file_path, content)

        # Detect language for code files
        detected_language = (
            self._detect_language(file_path) if classification == "PRACTICE" else None
        )

        # Create description from first few lines of content
        lines = content.split("\n")
        description = "\n".join(lines[:10]) if len(lines) > 10 else content
        if len(description) > 500:
            description = description[:500] + "..."

        # Create Resource using Dublin Core fields
        # Store file metadata in Dublin Core fields:
        # - identifier: relative path (for retrieval)
        # - source: absolute file path
        # - coverage: repo root path
        # - relation: [classification, language] for easy access
        resource = Resource(
            title=file_path.name,
            description=description,
            source=str(file_path),  # Original absolute file path
            identifier=relative_path_str,  # Relative path for retrieval
            coverage=str(root_path),  # Repo root path
            type="code_file" if classification == "PRACTICE" else "documentation",
            format=f"text/{detected_language}" if detected_language else "text/plain",
            language=detected_language,
            classification_code=classification,
            subject=[classification]
            + ([detected_language] if detected_language else []),
            relation=[f"classification:{classification}"]
            + ([f"language:{detected_language}"] if detected_language else []),
        )

        self.db.add(resource)
        await self.db.flush()  # Get the ID without committing

        logger.debug(
            f"Created resource: {relative_path_str} (classification={classification})"
        )

        return resource

    def _detect_language(self, file_path: Path) -> Optional[str]:
        """
        Detect programming language from file extension.

        Args:
            file_path: Path to the file

        Returns:
            Language name or None if unknown
        """
        extension_map = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".cpp": "cpp",
            ".c": "c",
            ".rb": "ruby",
            ".php": "php",
            ".swift": "swift",
            ".kt": "kotlin",
            ".scala": "scala",
            ".sh": "bash",
            ".bash": "bash",
        }

        extension = file_path.suffix.lower()
        return extension_map.get(extension)
