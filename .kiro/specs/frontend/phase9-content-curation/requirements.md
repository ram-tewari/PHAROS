# Phase 9: Content Curation Dashboard - Requirements

## Overview

**Phase**: 9
**Complexity**: ⭐⭐⭐ Medium (Option A: Clean & Fast)
**Dependencies**: Phase 1 (workbench) ✅
**Status**: Ready to implement

**Purpose**: Professional content curation dashboard for power users and administrators to review, improve, and maintain high-quality content through systematic workflows.

**Implementation Option**: **Option A: "Clean & Fast"** ⭐ RECOMMENDED
- **Style**: Dashboard-focused, data tables, efficient workflows
- **Components**: shadcn-ui Table, Badge, Dialog, Select + recharts
- **Interaction**: Filter, sort, batch select, review actions
- **Pros**: Clear, functional, efficient for curation tasks
- **Cons**: Basic visuals (but that's fine for admin tools)

---

## User Stories

### US-9.1: Review Queue Management
**As a** content curator  
**I want to** see a prioritized queue of resources needing review  
**So that** I can systematically improve content quality

**Acceptance Criteria**:
- [ ] Review queue displays resources below quality threshold
- [ ] Default threshold: 0.5 (configurable)
- [ ] Sort by quality score (lowest first), updated date
- [ ] Show resource title, type, quality score, last updated
- [ ] Pagination (25 items per page)
- [ ] Filter by status (pending/assigned/approved/rejected/flagged)
- [ ] Filter by quality score range (min/max sliders)
- [ ] Filter by assigned curator
- [ ] Click resource to view details

### US-9.2: Quality Analysis View
**As a** content curator  
**I want to** see detailed quality analysis for a resource  
**So that** I can understand what needs improvement

**Acceptance Criteria**:
- [ ] Overall quality score with color indicator
- [ ] Dimension scores (completeness, accuracy, clarity, relevance, freshness)
- [ ] Quality trend chart (if historical data available)
- [ ] Outlier status indicator
- [ ] Improvement suggestions (AI-generated)
- [ ] Resource metadata (title, type, created, updated)
- [ ] Quick actions (approve, reject, flag, assign)

### US-9.3: Batch Selection & Operations
**As a** content curator  
**I want to** select multiple resources and perform batch operations  
**So that** I can efficiently process many items

**Acceptance Criteria**:
- [ ] Checkbox selection for individual resources
- [ ] "Select all" checkbox for current page
- [ ] Selection counter (e.g., "5 selected")
- [ ] Batch actions dropdown: Approve, Reject, Flag, Tag, Assign
- [ ] Confirmation dialog for destructive actions
- [ ] Progress indicator for batch operations
- [ ] Success/error notifications with counts
- [ ] Clear selection after operation

### US-9.4: Batch Review Actions
**As a** content curator  
**I want to** approve, reject, or flag multiple resources at once  
**So that** I can quickly process review queue

**Acceptance Criteria**:
- [ ] Batch approve: Mark resources as approved
- [ ] Batch reject: Mark resources as rejected with optional reason
- [ ] Batch flag: Flag resources for expert review with notes
- [ ] Confirmation dialog shows count and action
- [ ] Optional notes field for batch actions
- [ ] Operation completes in < 5 seconds for 100 resources
- [ ] Partial success handling (show which failed)
- [ ] Refresh queue after operation

### US-9.5: Batch Tagging
**As a** content curator  
**I want to** add tags to multiple resources at once  
**So that** I can organize and categorize content efficiently

**Acceptance Criteria**:
- [ ] Tag input with autocomplete (existing tags)
- [ ] Add multiple tags (comma-separated or chips)
- [ ] Tags are case-insensitive and deduplicated
- [ ] Existing tags are preserved (additive operation)
- [ ] Preview: "Add tags to 5 resources"
- [ ] Success notification with count
- [ ] Tags appear immediately in resource list

### US-9.6: Curator Assignment
**As a** lead curator  
**I want to** assign resources to specific curators  
**So that** I can distribute workload and track responsibility

**Acceptance Criteria**:
- [ ] Curator dropdown (list of available curators)
- [ ] Batch assign: Assign multiple resources to one curator
- [ ] Assignment updates resource status to "assigned"
- [ ] Assigned curator shown in resource list
- [ ] Filter queue by assigned curator
- [ ] Unassign option (set to null)
- [ ] Assignment notification (optional)

### US-9.7: Low-Quality Resources List
**As a** content curator  
**I want to** see all low-quality resources in one view  
**So that** I can prioritize improvement efforts

**Acceptance Criteria**:
- [ ] Separate "Low Quality" tab/view
- [ ] Configurable quality threshold (default: 0.5)
- [ ] Sort by quality score (lowest first)
- [ ] Show quality score, title, type, last updated
- [ ] Batch selection and operations available
- [ ] Export to CSV option
- [ ] Pagination

### US-9.8: Bulk Quality Recalculation
**As a** system administrator  
**I want to** trigger quality recalculation for multiple resources  
**So that** I can update scores after algorithm changes

**Acceptance Criteria**:
- [ ] "Recalculate Quality" button in batch actions
- [ ] Confirmation dialog with resource count
- [ ] Progress indicator (percentage complete)
- [ ] Operation runs asynchronously
- [ ] Success notification when complete
- [ ] Updated scores reflected in UI
- [ ] Error handling for failed recalculations

### US-9.9: Quality Analytics Dashboard
**As a** content manager  
**I want to** see overall quality metrics and trends  
**So that** I can track content health over time

**Acceptance Criteria**:
- [ ] Quality score distribution chart (histogram)
- [ ] Average quality score (overall)
- [ ] Quality by resource type (bar chart)
- [ ] Quality trend over time (line chart)
- [ ] Low-quality resource count
- [ ] Recently reviewed count
- [ ] Curator activity summary
- [ ] Time range selector (7d, 30d, 90d, all)

### US-9.10: Resource Detail Modal
**As a** content curator  
**I want to** view and edit resource details in a modal  
**So that** I can review without leaving the queue

**Acceptance Criteria**:
- [ ] Modal opens on resource click
- [ ] Shows full resource metadata
- [ ] Quality analysis section
- [ ] Quick actions (approve, reject, flag)
- [ ] Edit tags inline
- [ ] Assign curator dropdown
- [ ] Add review notes
- [ ] Save changes button
- [ ] Close modal returns to queue

---

## Backend API Endpoints

All endpoints are in `backend/app/modules/curation/router.py`

### Review Queue
| Endpoint | Method | Request | Response | Purpose |
|----------|--------|---------|----------|---------|
| `/curation/queue` | GET | `status`, `assigned_to`, `min_quality`, `max_quality`, `limit`, `offset` | `ReviewQueueResponse` | Enhanced review queue with filters |
| `/curation/review-queue` | GET | `threshold`, `include_unread_only`, `limit`, `offset` | `ReviewQueueResponse` | Basic review queue |
| `/curation/low-quality` | GET | `threshold`, `limit`, `offset` | `LowQualityResponse` | Low-quality resources |

### Quality Analysis
| Endpoint | Method | Request | Response | Purpose |
|----------|--------|---------|----------|---------|
| `/curation/quality-analysis/{resource_id}` | GET | - | `QualityAnalysisResponse` | Detailed quality analysis |
| `/curation/bulk-quality-check` | POST | `resource_ids[]` | `BatchUpdateResult` | Bulk quality recalculation |

### Batch Operations
| Endpoint | Method | Request | Response | Purpose |
|----------|--------|---------|----------|---------|
| `/curation/batch/review` | POST | `resource_ids[]`, `action`, `reviewer_id`, `notes` | `BatchUpdateResult` | Batch approve/reject/flag |
| `/curation/batch/tag` | POST | `resource_ids[]`, `tags[]` | `BatchUpdateResult` | Batch tagging |
| `/curation/batch/assign` | POST | `resource_ids[]`, `curator_id` | `BatchUpdateResult` | Assign curator |
| `/curation/batch-update` | POST | `resource_ids[]`, `updates` | `BatchUpdateResult` | Generic batch update |

---

## Response Schemas

### ReviewQueueResponse
```typescript
interface ReviewQueueResponse {
  items: ReviewQueueItem[];
  total: number;
  limit: number;
  offset: number;
}

interface ReviewQueueItem {
  resource_id: string;
  title: string;
  resource_type: string;
  quality_score: number;
  status: 'pending' | 'assigned' | 'approved' | 'rejected' | 'flagged';
  assigned_to?: string;
  last_updated: string;
  created_at: string;
}
```

### QualityAnalysisResponse
```typescript
interface QualityAnalysisResponse {
  resource_id: string;
  overall_score: number;
  dimensions: {
    completeness: number;
    accuracy: number;
    clarity: number;
    relevance: number;
    freshness: number;
  };
  is_outlier: boolean;
  suggestions: string[];
  trend?: Array<{ date: string; score: number }>;
}
```

### BatchUpdateResult
```typescript
interface BatchUpdateResult {
  updated_count: number;
  failed_count: number;
  errors: Array<{
    resource_id: string;
    error: string;
  }>;
}
```

---

## UI Components Needed

### Pages
- `/curation` - Main curation dashboard

### Components
- `CurationLayout` - Dashboard layout
- `CurationHeader` - Title, filters, batch actions
- `ReviewQueueTable` - Main data table with selection
- `QualityAnalysisModal` - Detailed quality view
- `BatchActionsDropdown` - Batch operation selector
- `BatchConfirmDialog` - Confirmation for batch ops
- `QualityScoreBadge` - Color-coded quality indicator
- `StatusBadge` - Curation status indicator
- `TagInput` - Tag input with autocomplete
- `CuratorSelect` - Curator dropdown
- `QualityAnalyticsDashboard` - Charts and metrics
- `LowQualityView` - Low-quality resources tab
- `ResourceDetailModal` - Full resource details
- `ProgressIndicator` - Batch operation progress

---

## Non-Functional Requirements

### Performance
- Review queue loads in < 1 second
- Batch operations complete in < 5 seconds for 100 resources
- Table pagination smooth (no lag)
- Charts render in < 500ms

### Accessibility
- WCAG 2.1 AA compliant
- Keyboard navigation for table and modals
- Screen reader support for batch operations
- Clear focus indicators

### Responsiveness
- Desktop-first (1920x1080 primary)
- Tablet support (768px+)
- Mobile: Read-only view (optional)

### Error Handling
- Graceful handling of partial batch failures
- Clear error messages for users
- Retry option for failed operations
- Validation before batch operations

---

## Out of Scope

❌ **Automated Curation** - No AI auto-approval
❌ **Duplicate Detection** - No duplicate merging
❌ **Version History** - No resource version tracking
❌ **Workflow Automation** - No custom workflow builder
❌ **Email Notifications** - No email alerts for assignments
❌ **Advanced Analytics** - No ML-powered insights
❌ **Audit Log** - No detailed action history (use backend logs)
❌ **Role Management** - No curator role/permission UI

---

## Success Metrics

- [ ] All 10 user stories implemented
- [ ] Review queue displays correctly
- [ ] Batch operations work for 100+ resources
- [ ] Quality analysis modal shows all dimensions
- [ ] Filtering and sorting work correctly
- [ ] Batch selection and actions functional
- [ ] Zero accessibility violations
- [ ] Works on Chrome, Firefox, Safari

---

## Dependencies

### Phase 1 (Complete ✅)
- Workbench layout
- Sidebar navigation
- Theme system

### Backend (Complete ✅)
- Curation module with 9 endpoints
- Quality scoring integration
- Batch operation support
- Event system for tracking

### External Libraries
- shadcn-ui (Table, Dialog, Select, Badge)
- recharts (for analytics charts)
- TanStack Query (data fetching)
- TanStack Table (advanced table features)
- date-fns (date formatting)

---

## Related Documentation

- [Backend Curation Module](../../../backend/app/modules/curation/README.md)
- [Backend API Docs](../../../backend/docs/api/curation.md)
- [Phase 1 Spec](../phase1-workbench-navigation/requirements.md)
- [Frontend Roadmap](../ROADMAP.md)
