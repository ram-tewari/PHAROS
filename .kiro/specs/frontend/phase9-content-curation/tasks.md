# Phase 9: Content Curation Dashboard - Tasks (Option A: Clean & Fast)

## Overview

**Total Estimated Time**: 12-16 hours
**Complexity**: ⭐⭐⭐ Medium
**Team Size**: 1 developer

---

## Task Breakdown

### Stage 1: Foundation (2-3 hours)

#### Task 1.1: Setup Types & API Client
**Time**: 1 hour

- [ ] Create `src/types/curation.ts` with all response schemas
- [ ] Create `src/lib/api/curation.ts` with API client
- [ ] Add TanStack Query hooks in `src/lib/hooks/useCuration.ts`
- [ ] Test API integration with backend

**Files to Create**:
```
src/types/curation.ts
src/lib/api/curation.ts
src/lib/hooks/useCuration.ts
```

**Acceptance Criteria**:
- All TypeScript types match backend schemas
- API client successfully fetches from `/curation/*`
- TanStack Query hooks return typed data

---

#### Task 1.2: Create Zustand Store
**Time**: 30 minutes

- [ ] Create `src/stores/curationStore.ts`
- [ ] Implement filter state management
- [ ] Add selection state management
- [ ] Add tab navigation state

**Files to Create**:
```
src/stores/curationStore.ts
```

**Acceptance Criteria**:
- Store persists filter state
- Selection state updates correctly
- Tab navigation works

---

#### Task 1.3: Create Base Layout
**Time**: 1 hour

- [ ] Create `src/routes/_auth.curation.tsx`
- [ ] Create `src/components/curation/CurationLayout.tsx`
- [ ] Create `src/components/curation/CurationHeader.tsx`
- [ ] Add route to router configuration
- [ ] Add "Curation" link to sidebar navigation

**Files to Create**:
```
src/routes/_auth.curation.tsx
src/components/curation/CurationLayout.tsx
src/components/curation/CurationHeader.tsx
```

**Acceptance Criteria**:
- `/curation` route renders page
- Page header shows title and controls
- Layout uses responsive grid

---

#### Task 1.4: Create Reusable Components
**Time**: 30 minutes

- [ ] Create `src/components/curation/QualityScoreBadge.tsx`
- [ ] Create `src/components/curation/StatusBadge.tsx`
- [ ] Create `src/components/curation/FilterControls.tsx`

**Files to Create**:
```
src/components/curation/QualityScoreBadge.tsx
src/components/curation/StatusBadge.tsx
src/components/curation/FilterControls.tsx
```

**Acceptance Criteria**:
- Components are reusable and typed
- Quality badge shows correct colors
- Status badge displays correctly

---

### Stage 2: Review Queue (3-4 hours)

#### Task 2.1: Review Queue Table
**Time**: 2 hours

- [ ] Install TanStack Table: `npm install @tanstack/react-table`
- [ ] Create `src/components/curation/ReviewQueueTable.tsx`
- [ ] Implement column definitions
- [ ] Add checkbox selection column
- [ ] Add sortable columns
- [ ] Integrate with `useReviewQueue()` hook
- [ ] Add row click handler

**Files to Create**:
```
src/components/curation/ReviewQueueTable.tsx
```

**Acceptance Criteria**:
- Table displays review queue data
- Checkbox selection works
- Columns are sortable
- Row click opens detail modal
- Pagination works

---

#### Task 2.2: Filtering & Pagination
**Time**: 1 hour

- [ ] Implement status filter dropdown
- [ ] Implement quality range sliders
- [ ] Implement curator filter dropdown
- [ ] Add pagination controls
- [ ] Connect filters to API query

**Acceptance Criteria**:
- All filters work correctly
- Filters update query parameters
- Pagination navigates pages
- Filter state persists

---

#### Task 2.3: Selection & Batch Actions
**Time**: 1 hour

- [ ] Create `src/components/curation/BatchActionsDropdown.tsx`
- [ ] Implement selection summary ("5 selected")
- [ ] Add batch action handlers
- [ ] Create `src/components/curation/BatchConfirmDialog.tsx`
- [ ] Integrate with batch API mutations

**Files to Create**:
```
src/components/curation/BatchActionsDropdown.tsx
src/components/curation/BatchConfirmDialog.tsx
```

**Acceptance Criteria**:
- Batch actions dropdown shows when items selected
- Confirmation dialog appears before action
- Batch operations call API correctly
- Selection clears after operation

---

### Stage 3: Quality Analysis (2-3 hours)

#### Task 3.1: Quality Analysis Modal
**Time**: 1.5 hours

- [ ] Create `src/components/curation/QualityAnalysisModal.tsx`
- [ ] Display overall quality score
- [ ] Show dimension scores with progress bars
- [ ] Display AI-generated suggestions
- [ ] Add quick action buttons
- [ ] Integrate with `useQualityAnalysis()` hook

**Files to Create**:
```
src/components/curation/QualityAnalysisModal.tsx
```

**Acceptance Criteria**:
- Modal opens on resource click
- Quality scores display correctly
- Dimension scores show as progress bars
- Suggestions list displays
- Quick actions work

---

#### Task 3.2: Resource Detail Modal
**Time**: 1 hour

- [ ] Create `src/components/curation/ResourceDetailModal.tsx`
- [ ] Display full resource metadata
- [ ] Add inline tag editor
- [ ] Add curator assignment dropdown
- [ ] Add review notes textarea
- [ ] Implement save functionality

**Files to Create**:
```
src/components/curation/ResourceDetailModal.tsx
```

**Acceptance Criteria**:
- Modal shows complete resource details
- Tag editor works inline
- Curator assignment updates
- Review notes save correctly

---

#### Task 3.3: Bulk Quality Check
**Time**: 30 minutes

- [ ] Add "Recalculate Quality" to batch actions
- [ ] Create progress indicator component
- [ ] Implement bulk quality check mutation
- [ ] Show success/error notifications

**Acceptance Criteria**:
- Bulk quality check triggers API call
- Progress indicator shows during operation
- Success notification displays
- Updated scores reflect in table

---

### Stage 4: Low Quality View (1-2 hours)

#### Task 4.1: Low Quality Tab
**Time**: 1 hour

- [ ] Create `src/components/curation/LowQualityView.tsx`
- [ ] Add quality threshold slider
- [ ] Reuse ReviewQueueTable component
- [ ] Add export to CSV button
- [ ] Integrate with `useLowQualityResources()` hook

**Files to Create**:
```
src/components/curation/LowQualityView.tsx
```

**Acceptance Criteria**:
- Low quality tab displays correctly
- Threshold slider filters resources
- Table shows low-quality resources
- Export to CSV works

---

#### Task 4.2: Tab Navigation
**Time**: 30 minutes

- [ ] Create `src/components/curation/TabNavigation.tsx`
- [ ] Implement tab switching
- [ ] Connect to store state
- [ ] Add tab indicators

**Files to Create**:
```
src/components/curation/TabNavigation.tsx
```

**Acceptance Criteria**:
- Tabs switch views correctly
- Active tab highlighted
- Tab state persists

---

### Stage 5: Analytics Dashboard (2-3 hours)

#### Task 5.1: Quality Metrics Grid
**Time**: 1 hour

- [ ] Create `src/components/curation/QualityAnalyticsDashboard.tsx`
- [ ] Create metric cards (avg quality, low quality count, reviewed count, curator activity)
- [ ] Add time range selector
- [ ] Integrate with analytics API

**Files to Create**:
```
src/components/curation/QualityAnalyticsDashboard.tsx
```

**Acceptance Criteria**:
- Metrics display correctly
- Time range selector works
- Data updates on range change

---

#### Task 5.2: Quality Charts
**Time**: 1.5 hours

- [ ] Install recharts: `npm install recharts`
- [ ] Create quality distribution histogram
- [ ] Create quality by type bar chart
- [ ] Create quality trend line chart
- [ ] Add chart legends and tooltips

**Acceptance Criteria**:
- All 3 charts render correctly
- Charts are responsive
- Tooltips show exact values
- Time range affects trend chart

---

#### Task 5.3: Analytics Tab
**Time**: 30 minutes

- [ ] Add Analytics tab to navigation
- [ ] Integrate QualityAnalyticsDashboard
- [ ] Add loading states
- [ ] Add error handling

**Acceptance Criteria**:
- Analytics tab displays dashboard
- Charts load correctly
- Loading states show
- Errors handled gracefully

---

### Stage 6: Polish & Testing (2-3 hours)

#### Task 6.1: Error Handling
**Time**: 1 hour

- [ ] Add error boundaries to all sections
- [ ] Implement retry logic for failed requests
- [ ] Show partial failure details
- [ ] Add loading skeletons for all components
- [ ] Handle empty states

**Acceptance Criteria**:
- Errors display user-friendly messages
- Retry button works
- Loading states show skeletons
- Empty states show helpful messages

---

#### Task 6.2: Responsive Design
**Time**: 30 minutes

- [ ] Test on desktop (1920x1080)
- [ ] Test on tablet (768px)
- [ ] Adjust table columns for breakpoints
- [ ] Ensure modals are responsive

**Acceptance Criteria**:
- Desktop: Full table with all columns
- Tablet: Responsive table or horizontal scroll
- Modals resize correctly

---

#### Task 6.3: Accessibility
**Time**: 30 minutes

- [ ] Add ARIA labels to all actions
- [ ] Test keyboard navigation
- [ ] Test screen reader support
- [ ] Ensure color contrast meets WCAG AA
- [ ] Add focus indicators

**Acceptance Criteria**:
- All interactive elements keyboard accessible
- Screen reader announces updates
- Color contrast passes WCAG AA
- No accessibility violations in axe DevTools

---

#### Task 6.4: Performance Optimization
**Time**: 1 hour

- [ ] Implement virtual scrolling for large tables
- [ ] Debounce filter inputs
- [ ] Memoize expensive calculations
- [ ] Optimize re-renders
- [ ] Test with 1000+ resources

**Acceptance Criteria**:
- Table scrolls smoothly with 1000+ items
- Filters don't lag
- No unnecessary re-renders
- Performance meets targets

---

### Stage 7: Documentation (1 hour)

#### Task 7.1: Documentation
**Time**: 30 minutes

- [ ] Add JSDoc comments to all components
- [ ] Create README.md in `src/components/curation/`
- [ ] Document API integration
- [ ] Add usage examples

**Files to Create**:
```
src/components/curation/README.md
```

**Acceptance Criteria**:
- All components have JSDoc comments
- README explains feature and usage
- API integration documented

---

#### Task 7.2: Testing
**Time**: 30 minutes

- [ ] Write unit tests for key components
- [ ] Write integration tests for API hooks
- [ ] Test batch operations
- [ ] Test filter combinations
- [ ] Test selection logic

**Acceptance Criteria**:
- 80%+ code coverage
- All critical paths tested
- Tests pass in CI/CD

---

## File Structure

```
src/
├── routes/
│   └── _auth.curation.tsx
├── components/
│   └── curation/
│       ├── CurationLayout.tsx
│       ├── CurationHeader.tsx
│       ├── TabNavigation.tsx
│       ├── FilterControls.tsx
│       ├── QualityScoreBadge.tsx
│       ├── StatusBadge.tsx
│       ├── ReviewQueueTable.tsx
│       ├── BatchActionsDropdown.tsx
│       ├── BatchConfirmDialog.tsx
│       ├── QualityAnalysisModal.tsx
│       ├── ResourceDetailModal.tsx
│       ├── LowQualityView.tsx
│       ├── QualityAnalyticsDashboard.tsx
│       └── README.md
├── lib/
│   ├── api/
│   │   └── curation.ts
│   └── hooks/
│       └── useCuration.ts
├── stores/
│   └── curationStore.ts
└── types/
    └── curation.ts
```

---

## Dependencies to Install

```bash
npm install @tanstack/react-table recharts
```

---

## Testing Checklist

- [ ] All API endpoints return data
- [ ] Review queue displays correctly
- [ ] Filtering works (status, quality, curator)
- [ ] Sorting works on all columns
- [ ] Pagination navigates correctly
- [ ] Selection works (individual + select all)
- [ ] Batch actions work (approve, reject, flag, tag, assign)
- [ ] Confirmation dialogs appear
- [ ] Quality analysis modal displays
- [ ] Resource detail modal works
- [ ] Low quality view displays
- [ ] Analytics dashboard shows charts
- [ ] Time range selector works
- [ ] Bulk quality check works
- [ ] Error handling shows messages
- [ ] Loading states show skeletons
- [ ] Responsive design works
- [ ] Keyboard navigation works
- [ ] Screen reader support works
- [ ] Color contrast meets WCAG AA
- [ ] No console errors or warnings

---

## Success Criteria

- [ ] All 10 user stories implemented
- [ ] Review queue loads in < 1 second
- [ ] Batch operations complete in < 5 seconds for 100 resources
- [ ] All filters and sorting work correctly
- [ ] Quality analysis modal shows all dimensions
- [ ] Analytics dashboard displays 3 charts
- [ ] Zero accessibility violations
- [ ] Works on Chrome, Firefox, Safari
- [ ] 80%+ test coverage

---

## Related Documentation

- [Requirements](./requirements.md)
- [Design](./design.md)
- [Backend Curation API](../../../backend/docs/api/curation.md)
- [Frontend Roadmap](../ROADMAP.md)
