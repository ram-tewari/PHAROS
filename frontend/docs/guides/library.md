# Living Library User Guide

## Overview

The Living Library is Pharos's document management interface, providing powerful tools for organizing, viewing, and analyzing academic papers, code files, and other documents.

## Features

- **Document Management**: Upload, organize, and search documents
- **PDF Viewing**: Advanced PDF viewer with zoom, navigation, and highlighting
- **Collection Management**: Organize documents into collections
- **Scholarly Assets**: Extract and view equations, tables, and metadata
- **Auto-Linking**: Discover related papers and code files
- **Batch Operations**: Perform actions on multiple documents at once

---

## Getting Started

### Uploading Documents

1. Click the **Upload** button in the top-right corner
2. Drag and drop files or click to browse
3. Supported formats: PDF, HTML, TXT, MD
4. Maximum file size: 50MB per file
5. Multiple files can be uploaded at once

**Keyboard Shortcut**: `Ctrl+U` (Windows/Linux) or `Cmd+U` (Mac)

### Viewing Documents

1. Click on any document card in the grid
2. The PDF viewer opens in the right panel
3. Use the toolbar to navigate pages and zoom
4. Switch between tabs to view metadata, equations, tables, and related content

---

## Document Grid

### Layout

The document grid displays your library in a responsive layout:
- **Mobile**: 1 column
- **Tablet**: 2 columns
- **Desktop**: 3 columns
- **Large Desktop**: 4 columns

### Document Cards

Each card shows:
- **Thumbnail**: Preview image or file type icon
- **Title**: Document title
- **Authors**: Author names (truncated if long)
- **Date**: Publication or upload date
- **Quality Score**: AI-assessed quality percentage
- **Type Badge**: Document format (PDF, HTML, etc.)

### Actions

**Quick Actions** (hover over card):
- **Open**: View document in PDF viewer
- **Add to Collection**: Add to one or more collections
- **Delete**: Remove document from library

**Batch Selection**:
- Click checkbox in top-left of card
- Select multiple documents for batch operations

---

## Filtering & Search

### Search Bar

- Type to search document titles, authors, and content
- Search is debounced (300ms delay)
- Clear search with X button

### Filters

Click the **Filters** button to access:

**Document Type**:
- All types
- PDF
- HTML
- Code
- Text

**Quality Score Range**:
- Slider to set minimum and maximum quality
- Range: 0% to 100%
- Default: 0% to 100%

**Active Filters**:
- Displayed as badges below search bar
- Click X on badge to remove filter
- Click "Clear all" to reset all filters

### Sorting

Sort documents by:
- **Newest first** (default)
- **Oldest first**
- **Title A-Z**
- **Title Z-A**
- **Highest quality**
- **Lowest quality**

---

## PDF Viewer

### Navigation

**Page Controls**:
- Previous/Next buttons
- Page number input (type and press Enter)
- Total pages displayed
- Keyboard: Arrow Left/Right

**Zoom Controls**:
- Zoom In/Out buttons
- Zoom dropdown (50%, 75%, 100%, 125%, 150%, 200%)
- Fit to width button
- Keyboard: `Ctrl/Cmd +` (zoom in), `Ctrl/Cmd -` (zoom out), `Ctrl/Cmd 0` (reset)

**Actions**:
- Download PDF
- Print PDF

### Highlighting

1. Click the **Highlight** button in the toolbar
2. Select text in the PDF
3. Click **Highlight** in the popup
4. Choose highlight color from palette
5. Hover over highlight to delete

**Colors Available**:
- Yellow (default)
- Green
- Blue
- Pink
- Purple

---

## Collections

### Creating Collections

1. Click **Collections** in the header
2. Click **New** button
3. Enter collection name (required)
4. Add description (optional)
5. Add tags (optional)
6. Set visibility (public/private)
7. Click **Create**

### Managing Collections

**Edit Collection**:
- Click edit icon on collection card
- Update name, description, tags, or visibility
- Click **Save**

**Delete Collection**:
- Click delete icon on collection card
- Confirm deletion
- Note: Documents are not deleted, only removed from collection

**View Collection**:
- Click on collection card
- Documents in collection are displayed
- Collection statistics shown in sidebar

### Adding Documents to Collections

**Single Document**:
1. Click **Add to Collection** on document card
2. Select one or more collections
3. Click **Add to Collections**

**Multiple Documents**:
1. Select documents using checkboxes
2. Click **Add to Collection** in batch toolbar
3. Select collections
4. Click **Add to Collections**

**Inline Creation**:
- Click **Create New Collection** in picker dialog
- Enter name and click **Create**
- New collection is auto-selected

---

## Scholarly Assets

### Metadata Panel

View and edit document metadata:
- **Title**: Document title
- **Authors**: List of authors
- **Abstract**: Document summary
- **Keywords**: Subject keywords
- **Publication Date**: When published
- **DOI**: Digital Object Identifier
- **Journal**: Publication venue
- **Volume/Issue/Pages**: Citation details

**Completeness Indicator**:
- Shows percentage of filled fields
- Green (80%+): Complete
- Yellow (50-79%): Partial
- Red (<50%): Incomplete

**Editing**:
1. Click edit icon
2. Modify fields
3. Click save icon
4. Changes are saved to backend

### Equations

View all mathematical equations extracted from the document:

**Features**:
- Rendered LaTeX equations
- Equation numbers (if available)
- Page numbers
- LaTeX source code
- Search equations

**Actions**:
- **Copy LaTeX**: Copy source to clipboard
- **Jump to PDF**: Navigate to equation in PDF
- **Export All**: Download all equations as JSON

### Tables

View all tables extracted from the document:

**Features**:
- Rendered HTML tables
- Table captions
- Table numbers (if available)
- Page numbers
- Search tables

**Actions**:
- **Copy CSV**: Copy as comma-separated values
- **Copy JSON**: Copy as JSON array
- **Copy Markdown**: Copy as Markdown table
- **Jump to PDF**: Navigate to table in PDF
- **Export All**: Download all tables as JSON

---

## Auto-Linking

### Related Papers

Discover papers related to the current document:

**Relationship Types**:
- **Citation**: Papers that cite or are cited by this document
- **Semantic**: Papers with similar content
- **Reference**: Papers referenced in code or text

**Similarity Score**:
- Green (80%+): Highly similar
- Blue (60-79%): Moderately similar
- Yellow (40-59%): Somewhat similar
- Gray (<40%): Weakly similar

**Actions**:
- Click paper to open in viewer
- Click refresh to update suggestions

### Related Code

Discover code files related to the current document:

**Features**:
- Semantic similarity matching
- Code reference detection
- Similarity scores

**Actions**:
- Click code file to open in editor
- Click refresh to update suggestions

---

## Batch Operations

### Enabling Batch Mode

1. Click checkbox on any document card
2. Batch operations toolbar appears at bottom
3. Select additional documents

### Available Operations

**Add to Collection**:
1. Select documents
2. Click **Add to Collection**
3. Choose collections
4. Click **Add to Collections**

**Remove from Collection**:
1. Select documents (must be in a collection)
2. Click **Remove from Collection**
3. Choose collections
4. Click **Remove from Collections**

**Delete**:
1. Select documents
2. Click **Delete**
3. Confirm deletion
4. Documents are permanently removed

### Undo

- Click **Undo** button after add/remove operations
- Undo is not available for delete operations
- Undo is available for the last operation only

---

## Keyboard Shortcuts

### Global

- `Ctrl/Cmd + U`: Open upload dialog
- `Ctrl/Cmd + F`: Focus search bar
- `Ctrl/Cmd + K`: Open command palette
- `Escape`: Close dialogs/cancel selection

### PDF Viewer

- `Arrow Left`: Previous page
- `Arrow Right`: Next page
- `Ctrl/Cmd + +`: Zoom in
- `Ctrl/Cmd + -`: Zoom out
- `Ctrl/Cmd + 0`: Reset zoom
- `Ctrl/Cmd + P`: Print
- `Ctrl/Cmd + D`: Download

### Document Grid

- `Arrow Keys`: Navigate between documents
- `Enter`: Open selected document
- `Space`: Toggle selection
- `Ctrl/Cmd + A`: Select all documents
- `Ctrl/Cmd + D`: Deselect all

---

## Tips & Best Practices

### Organization

1. **Use Collections**: Group related documents for easy access
2. **Add Tags**: Use consistent tags for better filtering
3. **Complete Metadata**: Fill in metadata for better search results
4. **Quality Scores**: Review low-quality documents for accuracy

### Performance

1. **Virtual Scrolling**: Grid uses virtual scrolling for large libraries
2. **Lazy Loading**: Images load as you scroll
3. **Caching**: Frequently accessed documents are cached
4. **Batch Operations**: Use batch operations for multiple documents

### Search

1. **Use Filters**: Combine search with filters for precise results
2. **Quality Filter**: Find high-quality papers quickly
3. **Type Filter**: Filter by document format
4. **Sort Options**: Sort by relevance, date, or quality

### PDF Viewing

1. **Zoom Levels**: Use fit-to-width for reading
2. **Highlighting**: Use colors to categorize highlights
3. **Keyboard Navigation**: Use arrow keys for quick navigation
4. **Download**: Download PDFs for offline access

---

## Troubleshooting

### Upload Issues

**Problem**: Upload fails
- Check file size (max 50MB)
- Check file format (PDF, HTML, TXT, MD)
- Check internet connection
- Try again later

**Problem**: Upload is slow
- Large files take longer
- Check internet speed
- Upload during off-peak hours

### PDF Viewer Issues

**Problem**: PDF doesn't load
- Check file integrity
- Try downloading and re-uploading
- Check browser console for errors

**Problem**: PDF is blurry
- Increase zoom level
- Check PDF quality
- Try different browser

### Search Issues

**Problem**: No results found
- Check spelling
- Try broader search terms
- Clear filters
- Check if documents are uploaded

**Problem**: Wrong results
- Use more specific search terms
- Use filters to narrow results
- Check document metadata

### Collection Issues

**Problem**: Can't add to collection
- Check if collection exists
- Check permissions
- Try refreshing page

**Problem**: Collection is empty
- Check if documents were added
- Check filters
- Try refreshing page

---

## Advanced Features

### Metadata Extraction

- Automatic extraction from PDFs
- Manual editing available
- Completeness tracking
- Export to JSON

### Equation Recognition

- LaTeX rendering
- Equation numbering
- Page references
- Export capabilities

### Table Extraction

- HTML table rendering
- Multiple export formats
- Search within tables
- Page references

### Auto-Linking

- Citation network analysis
- Semantic similarity
- Code reference detection
- Refresh suggestions

---

## Accessibility

### Keyboard Navigation

- Full keyboard support
- Tab navigation
- Arrow key navigation
- Enter/Space for actions

### Screen Readers

- ARIA labels on all interactive elements
- Semantic HTML structure
- Alt text on images
- Status announcements

### Visual

- High contrast mode support
- Resizable text
- Color-blind friendly colors
- Focus indicators

---

## Support

For additional help:
- Check the [API Documentation](../api/library.md)
- Review [Component Documentation](../components/library.md)
- Submit issues on GitHub
- Contact support team

---

## Changelog

### Version 1.0.0 (Current)

- Initial release
- Document management
- PDF viewer
- Collection management
- Scholarly assets
- Auto-linking
- Batch operations
