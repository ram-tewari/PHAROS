# Steering Documentation Migration Guide

## Overview

This guide helps transition from monolithic documentation to the new modular steering structure.

## What Changed

### Before (Monolithic)
```
backend/README.md (50KB+)
├── Product overview
├── Tech stack
├── API documentation
├── Architecture details
├── Development guide
└── Everything else

Problem: Loading entire file for simple questions
```

### After (Modular)
```
AGENTS.md (2KB) - Routing rules
.kiro/steering/
├── product.md (3KB) - Product vision
├── tech.md (6KB) - Tech stack
└── structure.md (8KB) - Repo map

backend/docs/ - Detailed technical docs
.kiro/specs/ - Feature specifications

Benefit: Load only what's needed
```

## Migration Checklist

### For AI Agents

- [x] Create `AGENTS.md` with routing rules
- [x] Create steering docs (product, tech, structure)
- [x] Update `.kiro/README.md` to reference steering
- [ ] Update backend/README.md to reference steering
- [ ] Add steering links to key technical docs
- [ ] Train on new documentation patterns

### For Developers

- [ ] Read new steering docs
- [ ] Update bookmarks/references
- [ ] Use structure.md for navigation
- [ ] Follow new documentation patterns
- [ ] Update contribution guidelines

### For Documentation

- [ ] Add steering doc links to backend/README.md
- [ ] Add steering doc links to frontend/README.md
- [ ] Update DEVELOPER_GUIDE.md references
- [ ] Update CONTRIBUTING.md (if exists)
- [ ] Archive outdated documentation

## Mapping Old to New

### Product Questions

**Old**: Read entire backend/README.md
**New**: Read `.kiro/steering/product.md`

Examples:
- "What is Pharos?" → `product.md`
- "Who are the users?" → `product.md`
- "What are we NOT building?" → `product.md`

### Tech Stack Questions

**Old**: Search through backend/README.md
**New**: Read `.kiro/steering/tech.md`

Examples:
- "What database do we use?" → `tech.md`
- "How do I run tests?" → `tech.md`
- "What's the tech stack?" → `tech.md`

### Navigation Questions

**Old**: Search through file tree
**New**: Read `.kiro/steering/structure.md`

Examples:
- "Where is the API code?" → `structure.md`
- "How is the repo organized?" → `structure.md`
- "Where are the tests?" → `structure.md`

### API Questions

**Old**: backend/README.md or backend/docs/API_DOCUMENTATION.md
**New**: `backend/docs/API_DOCUMENTATION.md` (unchanged)

Note: API docs remain in place, steering docs just point to them

### Architecture Questions

**Old**: backend/README.md or backend/docs/ARCHITECTURE_DIAGRAM.md
**New**: `backend/docs/ARCHITECTURE_DIAGRAM.md` (unchanged)

Note: Architecture docs remain in place, steering docs provide overview

## Usage Examples

### Example 1: New Contributor

**Old workflow**:
1. Read entire backend/README.md (50KB)
2. Get overwhelmed
3. Ask questions

**New workflow**:
1. Read `AGENTS.md` (2KB) for routing
2. Read `product.md` (3KB) for vision
3. Read `tech.md` (6KB) for stack
4. Read `structure.md` (8KB) for navigation
5. Dive into relevant areas

Total: 19KB vs 50KB+ (60% reduction)

### Example 2: Implementing Feature

**Old workflow**:
1. Load backend/README.md
2. Load spec files
3. Load implementation files
4. Total: 80KB+ context

**New workflow**:
1. Read `AGENTS.md` for routing
2. Load feature spec only
3. Reference steering docs by path
4. Load implementation files as needed
5. Total: 30-40KB context

Savings: 50% context reduction

### Example 3: Answering Question

**Old workflow**:
1. Load backend/README.md
2. Search for answer
3. Maybe load other docs
4. Total: 50KB+ for simple question

**New workflow**:
1. Check `AGENTS.md` routing table
2. Load specific steering doc (2-8KB)
3. Answer found
4. Total: 2-8KB for simple question

Savings: 85% context reduction

## Transition Period

### Phase 1: Creation (Complete)
- ✅ Create steering docs
- ✅ Create AGENTS.md
- ✅ Update .kiro/README.md

### Phase 2: Integration (Current)
- [ ] Update backend/README.md
- [ ] Update frontend/README.md
- [ ] Add steering links to technical docs
- [ ] Update contribution guidelines

### Phase 3: Adoption (Next)
- [ ] Train team on new structure
- [ ] Update AI agent prompts
- [ ] Monitor usage patterns
- [ ] Gather feedback

### Phase 4: Optimization (Future)
- [ ] Archive outdated docs
- [ ] Consolidate redundant content
- [ ] Improve discoverability
- [ ] Measure effectiveness

## Backward Compatibility

### Existing Documentation
- All existing docs remain in place
- No breaking changes to current workflows
- Steering docs complement, not replace

### Existing Links
- All existing links continue to work
- New links point to steering docs
- Gradual migration of references

### Existing Workflows
- Current workflows still work
- New workflows are optional
- Gradual adoption encouraged

## Best Practices

### For AI Agents

1. **Start with routing**: Always check `AGENTS.md` first
2. **Load selectively**: Only load files needed for current task
3. **Reference by path**: Don't load docs "just in case"
4. **Close completed work**: Remove completed specs from context
5. **Ask if unsure**: Better to ask than load everything

### For Developers

1. **Read steering first**: Get high-level context before diving in
2. **Use structure.md**: Navigate with the map, not by searching
3. **Update as you go**: Keep docs in sync with code
4. **Follow hierarchy**: Start high-level, drill down as needed
5. **Contribute improvements**: Suggest doc improvements

### For Documentation

1. **Keep steering docs small**: <10KB per file
2. **Link, don't duplicate**: Reference detailed docs by path
3. **Update regularly**: Monthly or on major changes
4. **Maintain hierarchy**: Clear levels from high to low
5. **Measure effectiveness**: Track usage and feedback

## Troubleshooting

### "I can't find X"

1. Check `structure.md` for location
2. Check `AGENTS.md` routing table
3. Search in appropriate level of hierarchy
4. Ask for help if still unclear

### "Documentation is outdated"

1. Check last update date in file
2. Verify against current code
3. Submit update or create issue
4. Follow contribution guidelines

### "Too many docs to read"

1. Start with `AGENTS.md` routing
2. Read only relevant steering doc
3. Reference other docs by path
4. Load implementation files as needed

### "Not sure which doc to update"

1. Check steering doc hierarchy
2. Update at appropriate level
3. Link to detailed docs if needed
4. Ask for review if unsure

## Success Metrics

### Context Efficiency
- **Target**: 60% reduction in unnecessary file loading
- **Measure**: Track file loads per task
- **Goal**: <20KB for simple questions

### Discoverability
- **Target**: <30 seconds to find any documentation
- **Measure**: Time from question to answer
- **Goal**: 90% success rate

### Maintainability
- **Target**: Single file updates for most changes
- **Measure**: Files touched per doc update
- **Goal**: <2 files per update

### Adoption
- **Target**: 80% of team using new structure
- **Measure**: Survey and usage patterns
- **Goal**: Within 1 month

## Feedback

Please provide feedback on:
- Clarity of steering docs
- Ease of navigation
- Missing information
- Suggested improvements

Submit feedback via:
- GitHub issues
- Team discussions
- Direct messages
- Documentation PRs

## Next Steps

1. **Read steering docs**: Familiarize yourself with new structure
2. **Try new workflow**: Use steering docs for next task
3. **Provide feedback**: Share your experience
4. **Help others**: Guide teammates through transition
5. **Improve docs**: Suggest enhancements

## Questions?

- Check `AGENTS.md` for routing rules
- Check `.kiro/steering/README.md` for overview
- Ask in team discussions
- Create GitHub issue for doc improvements
