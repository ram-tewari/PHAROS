import re

with open('app/database/models.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = re.sub(r'class RecommendationFeedback\(Base\):.*?return f"<RecommendationFeedback.*?resource_id=\{self\.resource_id\!r\}\)>"\n', '', text, flags=re.DOTALL)
text = re.sub(r'class TaxonomyNode\(Base\):.*?(class ResourceTaxonomy\(Base\):)', r'\1', text, flags=re.DOTALL)
text = re.sub(r'@event\.listens_for\(TaxonomyNode, "before_insert"\)\n@event\.listens_for\(TaxonomyNode, "before_update"\)\ndef validate_taxonomy_node\(mapper, connection, target\):\n    """Validate taxonomy node before database operations\."""\n    target\.validate\(\)\n', '', text, flags=re.DOTALL)
text = re.sub(r'# Add validation event listeners for TaxonomyNode', '', text)
text = re.sub(r'class ResourceTaxonomy\(Base\):.*?return f"<ResourceTaxonomy.*?taxonomy_node_id=\{self\.taxonomy_node_id\!r\}\)>"\n', '', text, flags=re.DOTALL)
text = re.sub(r'class CurationReview\(Base\):.*?return f"<CurationReview.*?action=\{self\.action\!r\}\)>"\n', '', text, flags=re.DOTALL)

with open('app/database/models.py', 'w', encoding='utf-8') as f:
    f.write(text)
