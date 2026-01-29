# Phase 9: Content Curation Dashboard - Design (Option A: Clean & Fast)

## Architecture Overview

**Implementation**: Option A - "Clean & Fast" ⭐ RECOMMENDED
- Dashboard-focused with efficient data tables
- shadcn-ui for core components
- recharts for analytics
- TanStack Table for advanced table features
- Focus on functionality over fancy animations

```
┌─────────────────────────────────────────────────────────────┐
│              Curation Dashboard (/curation)                 │
│                  [Option A: Clean & Fast]                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────────┤
│  │ Header: Title | Filters | Batch Actions                │
│  └─────────────────────────────────────────────────────────┘
│                                                             │
│  ┌─────────────────────────────────────────────────────────┤
│  │ Tabs: Review Queue | Low Quality | Analytics           │
│  └─────────────────────────────────────────────────────────┘
│                                                             │
│  ┌─────────────────────────────────────────────────────────┤
│  │ Review Queue Table                                      │
│  ├─────────────────────────────────────────────────────────┤
│  │ [✓] Title | Type | Quality | Status | Assigned | Date  │
│  │ [✓] Resource 1 | Code | 0.45 | Pending | - | 2h ago    │
│  │ [ ] Resource 2 | PDF | 0.52 | Assigned | John | 1d ago │
│  │ [✓] Resource 3 | Code | 0.38 | Flagged | - | 3d ago    │
│  └─────────────────────────────────────────────────────────┘
│                                                             │
│  ┌─────────────────────────────────────────────────────────┤
│  │ Pagination: ← 1 2 3 ... 10 →                           │
│  └─────────────────────────────────────────────────────────┘
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Component Hierarchy

```
CurationPage
├── CurationLayout
│   ├── CurationHeader
│   │   ├── Title ("Content Curation")
│   │   ├── FilterControls
│   │   │   ├── StatusFilter (Select)
│   │   │   ├── QualityRangeFilter (Sliders)
│   │   │   └── CuratorFilter (Select)
│   │   └── BatchActionsDropdown
│   │       ├── BatchApprove
│   │       ├── BatchReject
│   │       ├── BatchFlag
│   │       ├── BatchTag
│   │       ├── BatchAssign
│   │       └── BulkQualityCheck
│   │
│   ├── TabNavigation
│   │   ├── ReviewQueueTab
│   │   ├── LowQualityTab
│   │   └── AnalyticsTab
│   │
│   ├── ReviewQueueView
│   │   ├── SelectionSummary ("5 selected")
│   │   ├── ReviewQueueTable (TanStack Table)
│   │   │   ├── SelectColumn (checkboxes)
│   │   │   ├── TitleColumn (clickable)
│   │   │   ├── TypeColumn (badge)
│   │   │   ├── QualityColumn (score + badge)
│   │   │   ├── StatusColumn (badge)
│   │   │   ├── AssignedColumn (curator name)
│   │   │   └── DateColumn (relative time)
│   │   └── Pagination
│   │
│   ├── LowQualityView
│   │   ├── ThresholdSlider
│   │   ├── LowQualityTable
│   │   └── ExportButton
│   │
│   └── AnalyticsView
│       ├── QualityMetricsGrid
│       │   ├── MetricCard (Avg Quality)
│       │   ├── MetricCard (Low Quality Count)
│       │   ├── MetricCard (Recently Reviewed)
│       │   └── MetricCard (Curator Activity)
│       ├── QualityDistributionChart (Histogram)
│       ├── QualityByTypeChart (Bar Chart)
│       └── QualityTrendChart (Line Chart)
│
├── QualityAnalysisModal
│   ├── ModalHeader (Resource Title)
│   ├── QualityScoreSection
│   │   ├── OverallScore (large number + badge)
│   │   └── DimensionScores (5 progress bars)
│   ├── SuggestionsSection
│   │   └── SuggestionList (AI-generated)
│   ├── MetadataSection
│   │   └── ResourceMetadata (type, dates, etc.)
│   └── QuickActions
│       ├── ApproveButton
│       ├── RejectButton
│       ├── FlagButton
│       └── AssignButton
│
├── BatchConfirmDialog
│   ├── DialogHeader (Action + Count)
│   ├── DialogContent
│   │   ├── ResourceList (preview)
│   │   └── NotesInput (optional)
│   └── DialogActions
│       ├── CancelButton
│       └── ConfirmButton
│
└── ResourceDetailModal
    ├── ModalHeader
    ├── ResourceContent (preview)
    ├── QualityAnalysis
    ├── TagEditor
    ├── CuratorAssignment
    ├── ReviewNotes
    └── SaveButton
```

---

## State Management

### Zustand Store: `useCurationStore`

```typescript
interface CurationStore {
  // Filters
  statusFilter: CurationStatus | 'all';
  minQuality: number;
  maxQuality: number;
  assignedToFilter: string | null;
  
  // Selection
  selectedIds: Set<string>;
  
  // UI State
  currentTab: 'queue' | 'low-quality' | 'analytics';
  qualityThreshold: number;
  
  // Actions
  setStatusFilter: (status: CurationStatus | 'all') => void;
  setQualityRange: (min: number, max: number) => void;
  setAssignedToFilter: (curator: string | null) => void;
  toggleSelection: (id: string) => void;
  selectAll: (ids: string[]) => void;
  clearSelection: () => void;
  setCurrentTab: (tab: string) => void;
  setQualityThreshold: (threshold: number) => void;
}
```

### TanStack Query Hooks

```typescript
// Review Queue
useReviewQueue(filters: ReviewQueueFilters, pagination: Pagination)
useLowQualityResources(threshold: number, pagination: Pagination)
useQualityAnalysis(resourceId: string)

// Batch Operations
useBatchReview() // mutation
useBatchTag() // mutation
useBatchAssign() // mutation
useBulkQualityCheck() // mutation

// Analytics
useQualityAnalytics(timeRange: string)
```

---

## API Integration

### Base Configuration

```typescript
// lib/api/curation.ts
import { apiClient } from './client';

const CURATION_BASE = '/curation';

export interface ReviewQueueFilters {
  status?: CurationStatus | 'all';
  assigned_to?: string;
  min_quality?: number;
  max_quality?: number;
  limit?: number;
  offset?: number;
}

export const curationApi = {
  // Review Queue
  getReviewQueue: (filters: ReviewQueueFilters) =>
    apiClient.get(`${CURATION_BASE}/queue`, { params: filters }),
  
  getLowQuality: (threshold: number, limit: number, offset: number) =>
    apiClient.get(`${CURATION_BASE}/low-quality`, {
      params: { threshold, limit, offset },
    }),
  
  getQualityAnalysis: (resourceId: string) =>
    apiClient.get(`${CURATION_BASE}/quality-analysis/${resourceId}`),
  
  // Batch Operations
  batchReview: (data: {
    resource_ids: string[];
    action: 'approve' | 'reject' | 'flag';
    reviewer_id: string;
    notes?: string;
  }) => apiClient.post(`${CURATION_BASE}/batch/review`, data),
  
  batchTag: (data: { resource_ids: string[]; tags: string[] }) =>
    apiClient.post(`${CURATION_BASE}/batch/tag`, data),
  
  batchAssign: (data: { resource_ids: string[]; curator_id: string }) =>
    apiClient.post(`${CURATION_BASE}/batch/assign`, data),
  
  bulkQualityCheck: (data: { resource_ids: string[] }) =>
    apiClient.post(`${CURATION_BASE}/bulk-quality-check`, data),
};
```

---

## Component Specifications

### 1. ReviewQueueTable

**Location**: `src/components/curation/ReviewQueueTable.tsx`

**Props**:
```typescript
interface ReviewQueueTableProps {
  data: ReviewQueueItem[];
  selectedIds: Set<string>;
  onToggleSelection: (id: string) => void;
  onSelectAll: (ids: string[]) => void;
  onRowClick: (item: ReviewQueueItem) => void;
}
```

**Features**:
- TanStack Table for advanced features
- Checkbox column for selection
- Sortable columns
- Row click opens detail modal
- Color-coded quality scores
- Status badges
- Relative time display

**Implementation**:
```typescript
const columns: ColumnDef<ReviewQueueItem>[] = [
  {
    id: 'select',
    header: ({ table }) => (
      <Checkbox
        checked={table.getIsAllPageRowsSelected()}
        onCheckedChange={(value) => table.toggleAllPageRowsSelected(!!value)}
      />
    ),
    cell: ({ row }) => (
      <Checkbox
        checked={row.getIsSelected()}
        onCheckedChange={(value) => row.toggleSelected(!!value)}
      />
    ),
  },
  {
    accessorKey: 'title',
    header: 'Title',
    cell: ({ row }) => (
      <button onClick={() => onRowClick(row.original)}>
        {row.original.title}
      </button>
    ),
  },
  // ... other columns
];
```

### 2. BatchActionsDropdown

**Location**: `src/components/curation/BatchActionsDropdown.tsx`

**Props**:
```typescript
interface BatchActionsDropdownProps {
  selectedIds: string[];
  onAction: (action: BatchAction) => void;
  disabled: boolean;
}
```

**Actions**:
- Approve
- Reject
- Flag
- Tag
- Assign
- Recalculate Quality

**Visual Design**:
- Dropdown menu (shadcn-ui DropdownMenu)
- Disabled when no selection
- Shows count in button label
- Icons for each action

### 3. QualityAnalysisModal

**Location**: `src/components/curation/QualityAnalysisModal.tsx`

**Props**:
```typescript
interface QualityAnalysisModalProps {
  resourceId: string;
  open: boolean;
  onClose: () => void;
  onAction: (action: 'approve' | 'reject' | 'flag') => void;
}
```

**Sections**:
1. **Overall Score** - Large number with color-coded badge
2. **Dimension Scores** - 5 progress bars (completeness, accuracy, clarity, relevance, freshness)
3. **Suggestions** - AI-generated improvement suggestions
4. **Metadata** - Resource type, dates, status
5. **Quick Actions** - Approve, Reject, Flag buttons

### 4. QualityScoreBadge

**Location**: `src/components/curation/QualityScoreBadge.tsx`

**Props**:
```typescript
interface QualityScoreBadgeProps {
  score: number;
  size?: 'sm' | 'md' | 'lg';
}
```

**Color Coding**:
- 0.0-0.4: Red (poor)
- 0.4-0.6: Yellow (needs improvement)
- 0.6-0.8: Blue (good)
- 0.8-1.0: Green (excellent)

### 5. BatchConfirmDialog

**Location**: `src/components/curation/BatchConfirmDialog.tsx`

**Props**:
```typescript
interface BatchConfirmDialogProps {
  open: boolean;
  action: BatchAction;
  count: number;
  onConfirm: (notes?: string) => void;
  onCancel: () => void;
}
```

**Content**:
- Action description (e.g., "Approve 5 resources")
- Optional notes input
- Preview of affected resources (first 5)
- Confirm/Cancel buttons

### 6. QualityAnalyticsDashboard

**Location**: `src/components/curation/QualityAnalyticsDashboard.tsx`

**Charts**:
1. **Quality Distribution** - Histogram showing score distribution
2. **Quality by Type** - Bar chart comparing resource types
3. **Quality Trend** - Line chart showing quality over time
4. **Metrics Grid** - 4 metric cards (avg quality, low quality count, reviewed count, curator activity)

**Time Range Selector**: 7d, 30d, 90d, all

---

## Styling & Theme

### Color Palette

**Quality Colors**:
- Poor (0.0-0.4): `red-500` (#ef4444)
- Needs Improvement (0.4-0.6): `yellow-500` (#eab308)
- Good (0.6-0.8): `blue-500` (#3b82f6)
- Excellent (0.8-1.0): `green-500` (#22c55e)

**Status Colors**:
- Pending: `gray-500`
- Assigned: `blue-500`
- Approved: `green-500`
- Rejected: `red-500`
- Flagged: `orange-500`

### Layout

**Table Style**:
- Striped rows for readability
- Hover effect on rows
- Fixed header on scroll
- Responsive columns

**Card Style**:
- Border: `border border-border`
- Background: `bg-card`
- Padding: `p-6`
- Rounded: `rounded-lg`

---

## Error Handling

### Scenarios

1. **Batch Operation Partial Failure**
   - Show success count and failed count
   - Display error details for failed items
   - Option to retry failed items

2. **API Timeout**
   - Show loading state
   - Timeout after 30 seconds
   - Retry button

3. **Invalid Selection**
   - Validate selection before batch operation
   - Show error if no items selected
   - Disable batch actions when invalid

### Error UI

```typescript
<Alert variant="destructive">
  <AlertTitle>Batch operation partially failed</AlertTitle>
  <AlertDescription>
    {result.updated_count} resources updated successfully.
    {result.failed_count} resources failed.
    <Button onClick={showErrors}>View Errors</Button>
  </AlertDescription>
</Alert>
```

---

## Performance Optimizations

1. **Virtual Scrolling** - For large tables (100+ items)
2. **Debounced Filters** - Debounce filter changes (300ms)
3. **Optimistic Updates** - Update UI immediately, rollback on error
4. **Pagination** - Load 25 items per page
5. **Memoization** - Memoize expensive calculations

---

## Accessibility

### Keyboard Navigation
- Tab through table rows
- Enter to open detail modal
- Space to toggle selection
- Arrow keys for table navigation

### Screen Reader Support
- ARIA labels for all actions
- ARIA live regions for batch operation results
- Table headers properly associated
- Status announced on change

---

## Testing Strategy

### Unit Tests
- Component rendering
- Filter logic
- Selection logic
- Batch operation handlers

### Integration Tests
- API integration
- Batch operations
- Filter combinations
- Pagination

### E2E Tests
- Full curation workflow
- Batch approve/reject/flag
- Quality analysis modal
- Analytics dashboard

---

## Related Documentation

- [Requirements](./requirements.md)
- [Tasks](./tasks.md)
- [Backend Curation API](../../../backend/docs/api/curation.md)
- [Phase 1 Design](../phase1-workbench-navigation/design.md)
