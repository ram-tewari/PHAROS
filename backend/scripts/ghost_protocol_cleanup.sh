#!/bin/bash
# Ghost Protocol: Module Cleanup Script
# 
# This script removes the "ghost" modules that were discovered in the audit:
# - planning module (dead code, not in use)
# - github module (standalone, functionality moved to resources module)
#
# Run from backend/ directory: bash scripts/ghost_protocol_cleanup.sh

set -e  # Exit on error

echo "🔍 Ghost Protocol: Module Cleanup"
echo "=================================="
echo ""

# Check we're in the backend directory
if [ ! -d "app/modules" ]; then
    echo "❌ Error: Must run from backend/ directory"
    exit 1
fi

# Backup before deletion
BACKUP_DIR="backups/ghost_modules_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "📦 Creating backup in $BACKUP_DIR..."

# Backup planning module
if [ -d "app/modules/planning" ]; then
    cp -r app/modules/planning "$BACKUP_DIR/"
    echo "  ✓ Backed up planning module"
fi

# Backup github module
if [ -d "app/modules/github" ]; then
    cp -r app/modules/github "$BACKUP_DIR/"
    echo "  ✓ Backed up github module"
fi

echo ""
echo "🗑️  Removing ghost modules..."

# Remove planning module
if [ -d "app/modules/planning" ]; then
    rm -rf app/modules/planning
    echo "  ✓ Removed app/modules/planning/"
else
    echo "  ⚠️  planning module not found (already removed?)"
fi

# Remove github module
if [ -d "app/modules/github" ]; then
    rm -rf app/modules/github
    echo "  ✓ Removed app/modules/github/"
else
    echo "  ⚠️  github module not found (already removed?)"
fi

echo ""
echo "🔍 Searching for import references..."

# Search for imports of removed modules
echo ""
echo "Planning module imports:"
grep -r "from.*modules.planning" app/ 2>/dev/null || echo "  ✓ No imports found"
grep -r "import.*modules.planning" app/ 2>/dev/null || echo "  ✓ No imports found"

echo ""
echo "GitHub module imports:"
grep -r "from.*modules.github" app/ 2>/dev/null || echo "  ✓ No imports found"
grep -r "import.*modules.github" app/ 2>/dev/null || echo "  ✓ No imports found"

echo ""
echo "📝 Manual cleanup required:"
echo "  1. Remove module registrations from app/main.py"
echo "  2. Remove event handlers from event bus"
echo "  3. Update documentation to reflect 13 active modules"
echo "  4. Run tests to verify no broken imports"
echo ""
echo "✅ Ghost Protocol cleanup complete!"
echo "   Backup saved to: $BACKUP_DIR"
