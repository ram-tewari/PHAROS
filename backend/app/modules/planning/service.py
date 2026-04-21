"""
Planning Module Services
"""

import os
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from .model import PlanningSession
from .schema import (
    PlanningResult,
    PlanningStep,
    ArchitectureParseResult,
    Component,
    Relationship,
    DesignPattern,
    ArchitectureGap,
)


class MultiHopAgent:
    """
    Multi-step planning agent with context preservation across planning steps.
    """

    def __init__(self, db: Session, llm_client: Optional[Any] = None):
        self.db = db
        self.llm_client = llm_client
        self.context_history: List[Dict[str, Any]] = []

    async def generate_plan(
        self, task_description: str, context: Dict[str, Any]
    ) -> PlanningResult:
        """
        Generate a multi-step implementation plan for a task.

        Args:
            task_description: Description of the task to plan
            context: Additional context for planning

        Returns:
            PlanningResult with steps and dependencies
        """
        # Generate unique plan ID
        plan_id = str(uuid.uuid4())

        # TODO: Use LLM to break down task into steps
        # For now, create a simple placeholder plan
        steps = [
            PlanningStep(
                step_id=1,
                description=f"Analyze requirements for: {task_description}",
                action_type="document",
                required_context=["requirements"],
                success_criteria="Requirements documented",
            ),
            PlanningStep(
                step_id=2,
                description="Design solution architecture",
                action_type="document",
                required_context=["requirements"],
                success_criteria="Architecture designed",
            ),
            PlanningStep(
                step_id=3,
                description="Implement core functionality",
                action_type="code",
                required_context=["requirements", "design"],
                success_criteria="Core features implemented",
            ),
            PlanningStep(
                step_id=4,
                description="Write tests",
                action_type="test",
                required_context=["implementation"],
                success_criteria="Tests passing",
            ),
            PlanningStep(
                step_id=5,
                description="Review and refine",
                action_type="review",
                required_context=["implementation", "tests"],
                success_criteria="Code reviewed and approved",
            ),
        ]

        # Extract dependencies (step 2 depends on 1, step 3 depends on 2, etc.)
        dependencies = [(i + 1, i) for i in range(1, len(steps))]

        # Store in database
        session = PlanningSession(
            id=plan_id,
            task_description=task_description,
            context=context,
            steps=[step.model_dump() for step in steps],
            dependencies=dependencies,
            status="active",
        )
        self.db.add(session)
        self.db.commit()

        # Update context history
        self.context_history.append(
            {
                "plan_id": plan_id,
                "task": task_description,
                "context": context,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

        return PlanningResult(
            plan_id=plan_id,
            steps=steps,
            dependencies=dependencies,
            estimated_duration="2-3 days",
            context_preserved=context,
        )

    async def refine_plan(self, plan_id: str, feedback: str) -> PlanningResult:
        """
        Refine an existing plan based on user feedback.

        Args:
            plan_id: ID of the plan to refine
            feedback: User feedback for refinement

        Returns:
            Updated PlanningResult
        """
        # Retrieve existing plan
        session = (
            self.db.query(PlanningSession).filter(PlanningSession.id == plan_id).first()
        )

        if not session:
            raise ValueError(f"Planning session {plan_id} not found")

        # TODO: Use LLM to refine plan based on feedback
        # For now, just add a new step based on feedback
        existing_steps = [PlanningStep(**step) for step in session.steps]
        new_step_id = len(existing_steps) + 1

        new_step = PlanningStep(
            step_id=new_step_id,
            description=f"Address feedback: {feedback}",
            action_type="code",
            required_context=["previous_steps"],
            success_criteria="Feedback addressed",
        )

        existing_steps.append(new_step)

        # Update dependencies
        dependencies = session.dependencies.copy()
        if len(existing_steps) > 1:
            dependencies.append((new_step_id, new_step_id - 1))

        # Update database
        session.steps = [step.model_dump() for step in existing_steps]
        session.dependencies = dependencies
        session.updated_at = datetime.utcnow()
        self.db.commit()

        # Update context history
        self.context_history.append(
            {
                "plan_id": plan_id,
                "action": "refine",
                "feedback": feedback,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

        return PlanningResult(
            plan_id=plan_id,
            steps=existing_steps,
            dependencies=dependencies,
            estimated_duration="2-3 days",
            context_preserved=session.context,
        )


class ArchitectureParser:
    """
    Service for extracting structured information from architecture documents.
    Leverages existing RepositoryParser to compare documented vs implemented architecture.
    """

    def __init__(self, db: Session, llm_client: Optional[Any] = None):
        self.db = db
        self.llm_client = llm_client
        # Import here to avoid circular dependencies
        from app.utils.repo_parser import RepositoryParser

        self.repo_parser = RepositoryParser()

    async def parse_architecture_doc(self, resource_id: int) -> ArchitectureParseResult:
        """
        Parse an architecture document to extract components, relationships, and patterns.

        Uses pattern matching and optional LLM to extract structured information.
        Compares with actual codebase structure using RepositoryParser.

        Args:
            resource_id: ID of the resource containing the architecture document

        Returns:
            ArchitectureParseResult with extracted information
        """
        # Retrieve resource from database
        from app.database.models import Resource, DocumentChunk

        resource = self.db.query(Resource).filter(Resource.id == resource_id).first()

        if not resource:
            raise ValueError(f"Resource {resource_id} not found")

        # Get document content from chunks
        chunks = (
            self.db.query(DocumentChunk)
            .filter(DocumentChunk.resource_id == resource_id)
            .order_by(DocumentChunk.chunk_index)
            .all()
        )

        # Concatenate chunk content
        content = "\n".join(chunk.content for chunk in chunks) if chunks else ""

        # If no chunks, try description field as fallback
        if not content and resource.description:
            content = resource.description

        if not content:
            # Return empty result if no content available
            return ArchitectureParseResult(
                components=[],
                relationships=[],
                patterns=[],
                gaps=[
                    ArchitectureGap(
                        gap_type="missing_component",
                        description="No content available for parsing",
                        severity="low",
                    )
                ],
            )

        # Extract components using pattern matching
        components = self._extract_components(content)

        # Extract relationships
        relationships = self._extract_relationships(content, components)

        # Identify design patterns
        patterns = self._identify_patterns(content, components, relationships)

        # Detect gaps between documented and implemented
        gaps = self._detect_gaps(resource, components, relationships)

        return ArchitectureParseResult(
            components=components,
            relationships=relationships,
            patterns=patterns,
            gaps=gaps,
        )

    def _extract_components(self, content: str) -> List[Component]:
        """
        Extract component names and descriptions from architecture document.

        Uses pattern matching to identify:
        - Section headers that look like component names
        - Bullet points describing responsibilities
        - Interface definitions

        Supports Markdown, reStructuredText, and plain text formats.

        Args:
            content: Document content

        Returns:
            List of Component objects
        """
        import re

        components = []

        # Pattern 1: Markdown headers (## Component Name)
        header_pattern = r"^#{1,3}\s+([A-Z][A-Za-z\s]+?)(?:\n|$)"
        headers = list(re.finditer(header_pattern, content, re.MULTILINE))

        for match in headers:
            component_name = match.group(1).strip()
            start_pos = match.end()

            # Extract description (text until next header or end)
            next_header = re.search(r"^#{1,3}\s+", content[start_pos:], re.MULTILINE)
            end_pos = start_pos + next_header.start() if next_header else len(content)
            description_text = content[start_pos:end_pos].strip()

            # Extract first paragraph as description
            description_lines = (
                description_text.split("\n\n")[0] if description_text else ""
            )
            description = description_lines.replace("\n", " ").strip()[:200]

            # Extract responsibilities (bullet points)
            responsibilities = []
            bullet_pattern = r"[-*]\s+(.+?)(?:\n|$)"
            for bullet_match in re.finditer(bullet_pattern, description_text):
                resp = bullet_match.group(1).strip()
                if len(resp) > 10 and len(resp) < 100:  # Filter noise
                    responsibilities.append(resp)

            # Extract interfaces (look for API, REST, GraphQL, etc.)
            interfaces = []
            interface_keywords = ["API", "REST", "GraphQL", "WebSocket", "gRPC", "HTTP"]
            for keyword in interface_keywords:
                if keyword.lower() in description_text.lower():
                    interfaces.append(keyword)

            # Only add if it looks like a real component
            if len(component_name) > 3 and len(component_name) < 50:
                components.append(
                    Component(
                        name=component_name,
                        description=description or f"{component_name} component",
                        responsibilities=responsibilities[:5],  # Limit to 5
                        interfaces=list(set(interfaces)),  # Remove duplicates
                    )
                )

        # Pattern 2: reStructuredText headers (Component Name\n----------)
        rst_pattern = r"^([A-Z][A-Za-z\s]+?)\n[-=]+\n"
        rst_headers = list(re.finditer(rst_pattern, content, re.MULTILINE))

        for match in rst_headers:
            component_name = match.group(1).strip()
            start_pos = match.end()

            # Extract description (text until next header or end)
            next_header = re.search(
                r"^[A-Z][A-Za-z\s]+?\n[-=]+\n", content[start_pos:], re.MULTILINE
            )
            end_pos = start_pos + next_header.start() if next_header else len(content)
            description_text = content[start_pos:end_pos].strip()

            # Extract first paragraph as description
            description_lines = (
                description_text.split("\n\n")[0] if description_text else ""
            )
            description = description_lines.replace("\n", " ").strip()[:200]

            # Extract responsibilities (bullet points with * or -)
            responsibilities = []
            bullet_pattern = r"[*-]\s+(.+?)(?:\n|$)"
            for bullet_match in re.finditer(bullet_pattern, description_text):
                resp = bullet_match.group(1).strip()
                if len(resp) > 10 and len(resp) < 100:
                    responsibilities.append(resp)

            # Extract interfaces
            interfaces = []
            interface_keywords = ["API", "REST", "GraphQL", "WebSocket", "gRPC", "HTTP"]
            for keyword in interface_keywords:
                if keyword.lower() in description_text.lower():
                    interfaces.append(keyword)

            # Only add if it looks like a real component and not already added
            if len(component_name) > 3 and len(component_name) < 50:
                if not any(c.name == component_name for c in components):
                    components.append(
                        Component(
                            name=component_name,
                            description=description or f"{component_name} component",
                            responsibilities=responsibilities[:5],
                            interfaces=list(set(interfaces)),
                        )
                    )

        # Pattern 3: Plain text with colons (Component Name:)
        # Match lines ending with colon
        colon_pattern = r"^([A-Z][A-Za-z\s0-9]+?):\s*$"
        colon_headers = list(re.finditer(colon_pattern, content, re.MULTILINE))

        for match in colon_headers:
            component_name = match.group(1).strip()
            start_pos = match.end() + 1  # Skip the newline

            # Extract description (text until next component or end)
            next_header = re.search(
                r"^[A-Z][A-Za-z\s0-9]+?:\s*$", content[start_pos:], re.MULTILINE
            )
            end_pos = start_pos + next_header.start() if next_header else len(content)
            description_text = content[start_pos:end_pos].strip()

            # Extract first paragraph as description
            description_lines = (
                description_text.split("\n\n")[0] if description_text else ""
            )
            description = description_lines.replace("\n", " ").strip()[:200]

            # Extract responsibilities
            responsibilities = []
            bullet_pattern = r"[-*]\s+(.+?)(?:\n|$)"
            for bullet_match in re.finditer(bullet_pattern, description_text):
                resp = bullet_match.group(1).strip()
                if len(resp) > 10 and len(resp) < 100:
                    responsibilities.append(resp)

            # Extract interfaces
            interfaces = []
            interface_keywords = ["API", "REST", "GraphQL", "WebSocket", "gRPC", "HTTP"]
            for keyword in interface_keywords:
                if keyword.lower() in description_text.lower():
                    interfaces.append(keyword)

            # Only add if it looks like a real component and not already added
            if len(component_name) > 3 and len(component_name) < 50:
                if not any(c.name == component_name for c in components):
                    components.append(
                        Component(
                            name=component_name,
                            description=description or f"{component_name} component",
                            responsibilities=responsibilities[:5],
                            interfaces=list(set(interfaces)),
                        )
                    )

        # Pattern 4: Component lists
        # Example: "Components: API Gateway, Service Layer, Database"
        component_list_pattern = (
            r"(?:Components?|Modules?|Services?):\s*([A-Z][A-Za-z\s,]+)"
        )
        for match in re.finditer(component_list_pattern, content, re.IGNORECASE):
            component_names = match.group(1).split(",")
            for name in component_names:
                name = name.strip()
                if len(name) > 3 and len(name) < 50:
                    # Check if not already added
                    if not any(c.name == name for c in components):
                        components.append(
                            Component(
                                name=name,
                                description=f"{name} component",
                                responsibilities=[],
                                interfaces=[],
                            )
                        )

        return components

    def _extract_relationships(
        self, content: str, components: List[Component]
    ) -> List[Relationship]:
        """
        Extract relationships between components.

        Looks for patterns like:
        - "A depends on B"
        - "A -> B"
        - "A calls B"
        - "A implements B"

        Args:
            content: Document content
            components: List of identified components

        Returns:
            List of Relationship objects
        """
        import re

        relationships = []
        component_names = [c.name for c in components]

        # Pattern 1: "A depends on B" / "A uses B" / "A calls B"
        for source_name in component_names:
            for target_name in component_names:
                if source_name == target_name:
                    continue

                # Check for dependency keywords
                patterns = [
                    rf"{re.escape(source_name)}\s+(?:depends on|uses|calls|requires)\s+{re.escape(target_name)}",
                    rf"{re.escape(source_name)}\s*-+>\s*{re.escape(target_name)}",
                    rf"{re.escape(source_name)}\s+implements\s+{re.escape(target_name)}",
                    rf"{re.escape(source_name)}\s+extends\s+{re.escape(target_name)}",
                ]

                for pattern in patterns:
                    if re.search(pattern, content, re.IGNORECASE):
                        # Determine relationship type
                        if "implements" in pattern.lower():
                            rel_type = "implements"
                        elif "extends" in pattern.lower():
                            rel_type = "extends"
                        else:
                            rel_type = "depends_on"

                        # Check if not already added
                        if not any(
                            r.source == source_name and r.target == target_name
                            for r in relationships
                        ):
                            relationships.append(
                                Relationship(
                                    source=source_name,
                                    target=target_name,
                                    relationship_type=rel_type,
                                    description=f"{source_name} {rel_type.replace('_', ' ')} {target_name}",
                                )
                            )
                        break

        return relationships

    def _identify_patterns(
        self,
        content: str,
        components: List[Component],
        relationships: List[Relationship],
    ) -> List[DesignPattern]:
        """
        Identify design patterns via pattern matching.

        Looks for mentions of common patterns:
        - Creational: Singleton, Factory, Builder
        - Structural: Adapter, Facade, Proxy, Layered
        - Behavioral: Observer, Strategy, Command

        Args:
            content: Document content
            components: List of components
            relationships: List of relationships

        Returns:
            List of DesignPattern objects
        """
        import re

        patterns = []

        # Define pattern keywords
        pattern_definitions = {
            "Singleton": ("creational", ["singleton", "single instance"]),
            "Factory": ("creational", ["factory", "factory method", "factory pattern"]),
            "Builder": ("creational", ["builder", "builder pattern"]),
            "Adapter": ("structural", ["adapter", "adapter pattern"]),
            "Facade": ("structural", ["facade", "facade pattern"]),
            "Proxy": ("structural", ["proxy", "proxy pattern"]),
            "Layered Architecture": (
                "structural",
                ["layered", "layers", "n-tier", "three-tier"],
            ),
            "Microservices": ("structural", ["microservices", "microservice"]),
            "Observer": (
                "behavioral",
                ["observer", "observer pattern", "pub-sub", "publish-subscribe"],
            ),
            "Strategy": ("behavioral", ["strategy", "strategy pattern"]),
            "Command": ("behavioral", ["command", "command pattern"]),
        }

        content_lower = content.lower()

        for pattern_name, (pattern_type, keywords) in pattern_definitions.items():
            # Check if any keyword is mentioned
            for keyword in keywords:
                if keyword in content_lower:
                    # Calculate confidence based on number of mentions
                    mentions = content_lower.count(keyword)
                    confidence = min(0.5 + (mentions * 0.1), 0.95)

                    # Identify involved components (heuristic: components mentioned near pattern keyword)
                    involved = []
                    for component in components:
                        # Search for component name within 200 chars of pattern keyword
                        pattern_positions = [
                            m.start()
                            for m in re.finditer(re.escape(keyword), content_lower)
                        ]
                        for pos in pattern_positions:
                            context = content[
                                max(0, pos - 200) : min(len(content), pos + 200)
                            ]
                            if component.name.lower() in context.lower():
                                involved.append(component.name)
                                break

                    patterns.append(
                        DesignPattern(
                            pattern_name=pattern_name,
                            pattern_type=pattern_type,
                            components_involved=list(set(involved))[
                                :5
                            ],  # Limit to 5, remove duplicates
                            confidence=confidence,
                        )
                    )
                    break  # Only add once per pattern

        return patterns

    def _detect_gaps(
        self,
        resource: Any,
        components: List[Component],
        relationships: List[Relationship],
    ) -> List[ArchitectureGap]:
        """
        Detect gaps between documented and implemented architecture.

        Uses RepositoryParser to analyze actual codebase structure if available.

        Args:
            resource: Resource object
            components: Documented components
            relationships: Documented relationships

        Returns:
            List of ArchitectureGap objects
        """
        gaps = []

        # Check if resource has repository path in source field (common pattern)
        # or if it's a local file path
        repo_path = None
        if resource.source and os.path.exists(resource.source):
            repo_path = resource.source

        if not repo_path:
            # Cannot compare without actual codebase
            # This is not really a gap, just a limitation
            return gaps

        try:
            # Use RepositoryParser to analyze actual codebase
            dependency_graph = self.repo_parser.build_dependency_graph(repo_path)

            # Check if documented components exist in codebase
            # Heuristic: Look for file/directory names matching component names
            for component in components:
                component_name_lower = component.name.lower().replace(" ", "_")
                found = False

                for file_path in dependency_graph.file_paths:
                    if component_name_lower in file_path.lower():
                        found = True
                        break

                if not found:
                    gaps.append(
                        ArchitectureGap(
                            gap_type="missing_component",
                            description=f"Component '{component.name}' documented but not found in codebase",
                            severity="medium",
                        )
                    )

            # Check for undocumented files (files in codebase but no matching component)
            documented_names = [c.name.lower().replace(" ", "_") for c in components]
            undocumented_count = 0

            for file_path in dependency_graph.file_paths[:10]:  # Sample first 10 files
                file_name = os.path.basename(file_path).lower()
                if not any(name in file_name for name in documented_names):
                    undocumented_count += 1

            if undocumented_count > 5:
                gaps.append(
                    ArchitectureGap(
                        gap_type="undocumented_relationship",
                        description=f"Found {undocumented_count} files with no corresponding documented components",
                        severity="low",
                    )
                )

        except Exception:
            # Log error but don't fail - gap detection is optional
            pass

        return gaps
