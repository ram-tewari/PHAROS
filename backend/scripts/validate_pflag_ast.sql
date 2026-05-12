-- Validation queries after re-ingesting pflag with the Go grammar.
-- If `non_block_ast_chunks` is 0, the dispatch layer isn't routing
-- Go files to the tree-sitter-go parser → check LANGUAGE_PARSERS.

-- Breakdown by ast_node_type for the pflag repo.
SELECT
    dc.ast_node_type,
    COUNT(*)                       AS chunk_count,
    COUNT(DISTINCT dc.resource_id) AS file_count
FROM document_chunks dc
JOIN resources r ON r.id = dc.resource_id
WHERE r.source ILIKE '%github.com/spf13/pflag%'
GROUP BY dc.ast_node_type
ORDER BY chunk_count DESC;

-- CI gate: must return > 0 for the re-ingest to be accepted.
-- 'block' is the fallback whole-file chunk emitted when no grammar matched.
SELECT COUNT(*) AS non_block_ast_chunks
FROM document_chunks dc
JOIN resources r ON r.id = dc.resource_id
WHERE r.source ILIKE '%github.com/spf13/pflag%'
  AND dc.ast_node_type IS NOT NULL
  AND dc.ast_node_type <> 'block';
