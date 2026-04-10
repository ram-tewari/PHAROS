# Issue Tracking Guidelines

## Purpose

This document defines the process for logging, tracking, and resolving issues in the Pharos backend. It ensures consistent documentation and helps maintain system quality over time.

## Issue Log Location

**Primary Log**: `backend/docs/ISSUES.md`

This file contains all identified issues, bugs, and technical debt across the Pharos backend implementation.

## When to Log an Issue

Log an issue when you encounter:

1. **Bugs**: Code that doesn't work as intended
2. **Type Errors**: Mismatches between expected and actual types
3. **Schema Mismatches**: Database schema doesn't match model definitions
4. **Missing Features**: TODOs or incomplete implementations
5. **Performance Problems**: Code that doesn't meet performance requirements
6. **Test Failures**: Consistent test failures indicating real issues
7. **Platform Issues**: Problems specific to SQLite, PostgreSQL, or other platforms
8. **Design Flaws**: Architectural issues that cause problems
9. **Technical Debt**: Code that works but needs refactoring

## Issue Template

Use this template when logging new issues:

```markdown
### ISSUE-YYYY-MM-DD-NNN: [Brief Title]

**ID**: ISSUE-YYYY-MM-DD-NNN  
**Phase**: [Phase 0-21 or General]  
**Category**: [Critical/Bug/Performance/Platform/Design/Testing/Feature]  
**Severity**: [Critical/High/Medium/Low]  
**Status**: [🔴 Open / 🟡 In Progress / ✅ Resolved]  
**Reported**: YYYY-MM-DD  
**Resolved**: YYYY-MM-DD (if applicable)  
**Reporter**: [Human/Agent/Test/System Component]

**Problem**:
[Clear description of the issue - what's wrong, what error occurs, what behavior is unexpected]

**Root Cause**:
[Why this happened - what design decision, missing requirement, or oversight led to this issue]

**Solution**:
[How it was fixed or how it should be fixed - specific steps taken or planned]

**Files Changed**:
- `path/to/file1.py`
- `path/to/file2.py`

**Impact**:
[What changed as a result - what features work now, what tests pass, what's improved]

**Prevention**:
[How to avoid this in the future - process changes, checks to add, patterns to follow]
```

## Issue ID Format

**Format**: `ISSUE-YYYY-MM-DD-NNN`

- **YYYY**: Year (e.g., 2026)
- **MM**: Month (e.g., 01 for January)
- **DD**: Day (e.g., 08)
- **NNN**: Sequential number for that day (001, 002, 003...)

**Examples**:
- `ISSUE-2026-01-08-001` - First issue reported on January 8, 2026
- `ISSUE-2026-02-16-003` - Third issue reported on February 16, 2026

## Severity Levels

### Critical
- System crashes or data loss
- Security vulnerabilities
- Complete feature failure
- Blocks deployment or major features

**Examples**:
- Database type mismatches causing query failures
- Authentication bypass vulnerabilities
- Data corruption issues

### High
- Major feature doesn't work as intended
- Significant performance degradation
- Many tests failing
- Affects multiple users or use cases

**Examples**:
- API endpoints not registered
- Model constructor parameter mismatches
- Missing database columns

### Medium
- Feature works but has limitations
- Minor performance issues
- Some tests failing
- Workarounds available

**Examples**:
- TODO features not implemented
- Performance thresholds too strict
- Optional dependencies missing

### Low
- Minor inconveniences
- Cosmetic issues
- Documentation gaps
- Nice-to-have improvements

**Examples**:
- Log message improvements
- Optional feature warnings
- Documentation typos

## Category Types

- **Critical**: System-breaking issues
- **Bug**: Code that doesn't work correctly
- **Performance**: Speed or resource usage issues
- **Platform**: SQLite vs PostgreSQL compatibility issues
- **Design**: Architectural or design flaws
- **Testing**: Test suite issues
- **Feature**: Missing or incomplete features

## Status Values

- **🔴 Open**: Issue identified but not yet addressed
- **🟡 In Progress**: Actively being worked on
- **✅ Resolved**: Fixed and verified

## Issue Workflow

### 1. Discovery
- Encounter issue during development, testing, or code review
- Verify it's a real issue (not expected behavior)
- Check if already logged in ISSUES.md

### 2. Documentation
- Create issue entry using template
- Assign appropriate severity and category
- Document problem, root cause, and proposed solution
- Add to correct section in ISSUES.md (Critical/High/Medium/Low)

### 3. Resolution
- Implement fix
- Update issue with solution details
- List all files changed
- Document impact and prevention measures
- Change status to ✅ Resolved
- Add resolved date
- Move to "Resolved Issues" section

### 4. Verification
- Verify fix works in all environments (SQLite, PostgreSQL)
- Ensure tests pass
- Check for regression
- Update documentation if needed

## Where to Place Issues in ISSUES.md

Issues are organized by severity:

1. **Critical Issues** - Top of file, highest visibility
2. **High Priority Issues** - Second section
3. **Medium Priority Issues** - Third section
4. **Low Priority Issues** - Fourth section
5. **Resolved Issues** - Bottom section (historical record)

Within each section, issues are ordered chronologically (newest first).

## Issue Statistics

Update the statistics section at the bottom of ISSUES.md when adding or resolving issues:

```markdown
## Issue Statistics

**Total Issues Logged**: [count]  
**Critical**: [count] ([resolved] resolved, [open] open)  
**High Priority**: [count] ([resolved] resolved, [open] open)  
**Medium Priority**: [count] ([resolved] resolved, [open] open)  
**Low Priority**: [count] ([resolved] resolved, [open] open)

**Resolution Rate**: [percentage]  
**Open Issues**: [count]  
**Resolved Issues**: [count]
```

## Common Issue Patterns

### Database Schema Issues

**Pattern**: Model fields don't match database columns

**Template**:
```markdown
**Problem**: Tests query by field X but column doesn't exist in database
**Root Cause**: Model added field without migration
**Solution**: Create Alembic migration to add column
**Prevention**: Always create migrations when adding model fields
```

### Type Mismatch Issues

**Pattern**: PostgreSQL vs SQLite type differences

**Template**:
```markdown
**Problem**: Boolean columns stored as INTEGER in PostgreSQL
**Root Cause**: SQLite compatibility approach used INTEGER
**Solution**: Create migration to convert INTEGER to BOOLEAN for PostgreSQL
**Prevention**: Use database-agnostic type checking in migrations
```

### Missing Feature Issues

**Pattern**: TODO comments in code

**Template**:
```markdown
**Problem**: Feature X marked as TODO, not implemented
**Root Cause**: Feature deferred during initial implementation
**Solution**: Implement feature with [specific approach]
**Prevention**: Track TODOs in issue tracker, prioritize in roadmap
```

### Test Failure Issues

**Pattern**: Tests fail due to incorrect expectations

**Template**:
```markdown
**Problem**: Tests expect X but system returns Y
**Root Cause**: Test expectations don't match actual behavior
**Solution**: Update tests to match correct system behavior
**Prevention**: Update tests alongside implementation changes
```

## Integration with Development Workflow

### During Development
1. Check ISSUES.md for known issues in area you're working on
2. Log new issues as you discover them
3. Update issue status when making progress

### During Code Review
1. Check if PR addresses any open issues
2. Update issue status if PR resolves issues
3. Log new issues discovered during review

### During Testing
1. Check if test failures match known issues
2. Log new issues for unexpected failures
3. Update issue status when tests pass

### During Deployment
1. Review open Critical and High issues
2. Ensure no blockers for deployment
3. Document any issues discovered in production

## Best Practices

### DO:
- ✅ Log issues as soon as you discover them
- ✅ Provide clear, detailed descriptions
- ✅ Include error messages and stack traces
- ✅ Document root cause analysis
- ✅ Update status when working on issues
- ✅ Move resolved issues to Resolved section
- ✅ Keep statistics up to date

### DON'T:
- ❌ Skip logging issues "to fix later"
- ❌ Use vague descriptions like "doesn't work"
- ❌ Leave issues in wrong severity category
- ❌ Forget to update status when resolving
- ❌ Delete resolved issues (keep for history)
- ❌ Log duplicate issues without checking first

## Searching for Issues

### By ID
Search for exact ID: `ISSUE-2026-01-08-001`

### By Phase
Search for phase: `Phase 17` or `Phase 10`

### By Category
Search for category: `Category: Critical` or `Category: Bug`

### By Status
Search for status: `Status: 🔴 Open` or `Status: ✅ Resolved`

### By Keyword
Search for keywords in problem description: `boolean`, `embedding`, `PostgreSQL`

## Related Documentation

- [Issue Log](../../backend/docs/ISSUES.md) - Complete issue history
- [Tech Stack](tech.md) - Technology constraints and requirements
- [Repository Structure](structure.md) - Where to find code
- [Product Overview](product.md) - What we're building

## Examples

### Example 1: Critical Database Issue

```markdown
### ISSUE-2026-01-08-001: Boolean Column Type Mismatch (PostgreSQL)

**ID**: ISSUE-2026-01-08-001  
**Phase**: Phase 13 (PostgreSQL Migration)  
**Category**: Critical/Platform  
**Severity**: Critical  
**Status**: ✅ Resolved  
**Reported**: 2026-01-08  
**Resolved**: 2026-01-08  
**Reporter**: Migration System

**Problem**:
Boolean columns in resources table stored as INTEGER instead of BOOLEAN in PostgreSQL, causing type errors.

**Root Cause**:
Initial migrations used INTEGER for SQLite compatibility without PostgreSQL-specific handling.

**Solution**:
Created migration that converts INTEGER to BOOLEAN using CASE statements.

**Files Changed**:
- `backend/alembic/versions/20260108_fix_boolean_columns.py`

**Impact**:
- Fixed PostgreSQL query type errors
- Improved schema correctness
- Maintained SQLite compatibility

**Prevention**:
- Use database-agnostic type checking
- Test migrations on both databases
- Document platform-specific handling
```

### Example 2: Medium Priority TODO

```markdown
### ISSUE-2026-01-XX-001: TODO - Author Normalization Not Implemented

**ID**: ISSUE-2026-01-XX-001  
**Phase**: General  
**Category**: Medium/Feature  
**Severity**: Medium  
**Status**: 🔴 Open  
**Reported**: 2026-01-XX  
**Reporter**: Code Review

**Problem**:
Author normalization marked as TODO. Authors stored in inconsistent formats.

**Root Cause**:
Feature deferred during initial implementation.

**Solution**:
Implement normalization that:
1. Standardizes name formats
2. Handles initials
3. Deduplicates authors
4. Links works by same author

**Files Changed**:
- `backend/app/tasks/celery_tasks.py` (line 398-400)

**Impact**:
- Improved author search
- Better citation analysis
- Cleaner metadata

**Prevention**:
- Track TODOs in issue tracker
- Prioritize data quality features
- Add to roadmap
```

## Maintenance

### Weekly Review
- Review open issues
- Update priorities
- Close resolved issues
- Update statistics

### Monthly Review
- Analyze issue patterns
- Identify systemic problems
- Update prevention strategies
- Review resolution rate

### Quarterly Review
- Assess issue tracking effectiveness
- Update guidelines if needed
- Archive very old resolved issues
- Generate trend reports

---

**Remember**: Good issue tracking is essential for maintaining code quality and preventing regressions. When in doubt, log it!
