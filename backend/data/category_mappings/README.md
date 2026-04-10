# Category Mapping Files

This directory contains JSON files that map external dataset categories to Pharos's taxonomy node IDs.

## Purpose

When training models on external datasets (arXiv, AG News, Wikipedia, etc.), we need to map their category systems to our internal taxonomy. These mapping files provide that translation layer.

## File Format

```json
{
  "name": "Dataset Name to Pharos Taxonomy Mapping",
  "version": "1.0",
  "description": "Brief description",
  "created": "2025-11-16",
  "mappings": {
    "external_category_1": ["taxonomy-node-id-1"],
    "external_category_2": ["taxonomy-node-id-2", "taxonomy-node-id-3"],
    "external_category_3": ["taxonomy-node-id-1"]
  },
  "notes": {
    "external_category_1": "Optional description"
  }
}
```

## Available Mappings

### arxiv_mapping.json
Maps arXiv categories (cs.AI, cs.LG, etc.) to taxonomy nodes.

**Usage:**
```bash
python backend/scripts/load_external_data.py \
  --dataset arxiv \
  --data-path data/external/arxiv/arxiv-metadata-oai-snapshot.json \
  --mapping-file backend/data/category_mappings/arxiv_mapping.json \
  --output data/processed/arxiv_training.json
```

### ag_news_mapping.json
Maps AG News categories (world, sports, business, sci-tech) to taxonomy nodes.

**Usage:**
```bash
python backend/scripts/load_external_data.py \
  --dataset ag_news \
  --mapping-file backend/data/category_mappings/ag_news_mapping.json \
  --output data/processed/ag_news_training.json
```

## Creating New Mappings

1. **Identify external categories**: Review the external dataset's category system
2. **Map to taxonomy nodes**: Determine which taxonomy nodes best represent each external category
3. **Support multi-label**: One external category can map to multiple taxonomy nodes
4. **Document rationale**: Add notes explaining mapping decisions
5. **Version control**: Commit mapping files to track changes

## Example: Creating Wikipedia Mapping

```json
{
  "name": "Wikipedia to Pharos Taxonomy Mapping",
  "version": "1.0",
  "mappings": {
    "Category:Machine_learning": ["ml-node-1"],
    "Category:Artificial_intelligence": ["ml-node-1"],
    "Category:Natural_language_processing": ["nlp-node-1"],
    "Category:Computer_vision": ["cv-node-1"],
    "Category:Databases": ["db-node-1"],
    "Category:Computer_security": ["sec-node-1"],
    "Category:Cloud_computing": ["cloud-node-1"],
    "Category:Quantum_computing": ["qc-node-1"],
    "Category:Algorithms": ["algo-node-1"],
    "Category:Blockchain": ["bc-node-1"],
    "Category:Web_development": ["web-node-1"]
  }
}
```

## Best Practices

1. **Be conservative**: Only map categories you're confident about
2. **Avoid over-mapping**: Don't force unrelated categories to match
3. **Use hierarchies**: Map parent categories to broader taxonomy nodes
4. **Test mappings**: Validate with sample data before full training
5. **Document decisions**: Explain non-obvious mappings in notes
6. **Version mappings**: Update version when making significant changes

## Taxonomy Node IDs

Current taxonomy nodes in the system:
- `ml-node-1`: Machine Learning
- `dl-node-1`: Deep Learning
- `nlp-node-1`: Natural Language Processing
- `cv-node-1`: Computer Vision
- `db-node-1`: Databases
- `sec-node-1`: Cybersecurity
- `cloud-node-1`: Cloud Computing
- `qc-node-1`: Quantum Computing
- `algo-node-1`: Algorithms
- `bc-node-1`: Blockchain
- `web-node-1`: Web Development

To see the full taxonomy, query the database:
```sql
SELECT id, name, description FROM taxonomy_nodes;
```
