"use client"

import * as React from "react"

/**
 * Localized copy for the vendored Extend UI viewers.
 *
 * The official registry components hard-code English labels. Clouisle wraps
 * them in this provider so tooltips, controls, menus, and state surfaces follow
 * the active locale. Components fall back to English when used standalone.
 */
export type ViewerLabels = {
  loading: string
  download: string
  upload: string
  darkMode: string
  zoomIn: string
  zoomOut: string
  zoomLevel: string
  zoom: string
  fitPage: string
  fitWidth: string
  automatic: string
  searchText: string
  searchWorkbook: string
  searchCsv: string
  searching: string
  noSearch: string
  noResults: string
  previousResult: string
  nextResult: string
  clear: string
  page: string
  pageNumber: string
  currentPage: (values: { page: number }) => string
  pageTotal: (values: { total: number | string }) => string
  pageLabel: (values: { page: number }) => string
  pagesSidebar: string
  toggleThumbnails: string
  rotateCounterclockwise: string
  rotateClockwise: string
  pagesRegion: string
  openPdfActions: string
  pdfLoadError: string
  pdfEngineLoadError: string
  pdfEmptyTitle: string
  pdfEmptyDescription: string
  docxLoadError: string
  docxLoadErrorTitle: string
  docxEmptyTitle: string
  docxEmptyDescription: string
  docxEmptyLegacy: string
  docxUpload: string
  docxPages: string
  docxDocumentRegion: string
  comments: string
  edits: string
  inserted: string
  removed: string
  movedFrom: string
  movedTo: string
  resolved: string
  reply: string
  comment: string
  unknownAuthor: string
  openDocxActions: string
  xlsxLoadError: string
  xlsxEmptyTitle: string
  xlsxEmptyDescription: string
  xlsxUpload: string
  xlsxTooLargeTitle: string
  xlsxTooLargeDescription: string
  openWorkbookActions: string
  columnMenu: string
  sortAscending: string
  sortDescending: string
  xlsxActions: Record<string, string>
  sheetPreview: (values: { name: string }) => string
  pptxLoadError: string
  pptxEmptyTitle: string
  pptxEmptyDescription: string
  pptxUpload: string
  pptxNoSlides: string
  slide: string
  slideLabel: (values: { slide: number }) => string
  slideTotal: (values: { total: number | string }) => string
  slideNumber: string
  currentSlide: (values: { slide: number }) => string
  previousSlide: string
  nextSlide: string
  slidesRegion: string
  presentationRegion: string
  openPresentationActions: string
  csvParseError: string
  csvReadError: string
  csvEmptyTitle: string
  csvEmptyDescription: string
  csvUpload: string
  columnName: (values: { index: number }) => string
  extraColumnName: (values: { index: number }) => string
  openCsvActions: string
}

export const DEFAULT_VIEWER_LABELS: ViewerLabels = {
  loading: "Loading",
  download: "Download",
  upload: "Upload",
  darkMode: "Dark mode",
  zoomIn: "Zoom in",
  zoomOut: "Zoom out",
  zoomLevel: "Zoom level",
  zoom: "Zoom",
  fitPage: "Fit page",
  fitWidth: "Fit width",
  automatic: "Automatic",
  searchText: "Search text",
  searchWorkbook: "Search workbook",
  searchCsv: "Search CSV",
  searching: "Searching",
  noSearch: "No search",
  noResults: "No results",
  previousResult: "Previous result",
  nextResult: "Next result",
  clear: "Clear",
  page: "Page",
  pageNumber: "Page number",
  currentPage: ({ page }) => `Current page ${page}. Edit page number`,
  pageTotal: ({ total }) => `of ${total}`,
  pageLabel: ({ page }) => `Page ${page}`,
  pagesSidebar: "Pages sidebar",
  toggleThumbnails: "Toggle thumbnails",
  rotateCounterclockwise: "Rotate counterclockwise",
  rotateClockwise: "Rotate clockwise",
  pagesRegion: "PDF pages",
  openPdfActions: "Open PDF actions",
  pdfLoadError: "Unable to load the PDF preview.",
  pdfEngineLoadError: "Unable to load the PDF engine.",
  pdfEmptyTitle: "Upload a PDF to preview",
  pdfEmptyDescription:
    "Pass a PDF URL with the src prop or use the upload control.",
  docxLoadError: "Unable to load the DOCX preview.",
  docxLoadErrorTitle: "Unable to display DOCX",
  docxEmptyTitle: "Upload a Word document to preview",
  docxEmptyDescription: "Pass a DOCX URL with the src prop or upload a file.",
  docxEmptyLegacy:
    "Legacy .doc support is limited and experimental; convert to DOCX for best fidelity.",
  docxUpload: "Upload Word document",
  docxPages: "DOCX pages",
  docxDocumentRegion: "DOCX document",
  comments: "Comments",
  edits: "Edits",
  inserted: "Inserted",
  removed: "Removed",
  movedFrom: "Moved from",
  movedTo: "Moved to",
  resolved: "Resolved",
  reply: "Reply",
  comment: "Comment",
  unknownAuthor: "Unknown author",
  openDocxActions: "Open DOCX actions",
  xlsxLoadError: "Unable to load the workbook.",
  xlsxEmptyTitle: "Upload a workbook to preview",
  xlsxEmptyDescription:
    "Pass an XLSX URL with the src prop or upload a file.",
  xlsxUpload: "Upload workbook",
  xlsxTooLargeTitle: "File too large",
  xlsxTooLargeDescription:
    "This workbook exceeds the display limit. Download it to view the full file.",
  openWorkbookActions: "Open workbook actions",
  columnMenu: "Column menu",
  sortAscending: "Sort ascending",
  sortDescending: "Sort descending",
  xlsxActions: {
    cut: "Cut",
    copy: "Copy",
    paste: "Paste",
    clearContents: "Clear contents",
    editCell: "Edit cell",
    undo: "Undo",
    redo: "Redo",
    mergeCells: "Merge cells",
    mergeAndCenter: "Merge and center",
    mergeAcross: "Merge across",
    unmergeCells: "Unmerge cells",
    sortAscending: "Sort ascending",
    sortDescending: "Sort descending",
    selectRow: "Select row",
    selectColumn: "Select column",
    selectAll: "Select all",
  },
  sheetPreview: ({ name }) => `${name} preview`,
  pptxLoadError: "Unable to display PowerPoint",
  pptxEmptyTitle: "Upload a PowerPoint presentation to preview",
  pptxEmptyDescription:
    "Pass a PPTX URL with the src prop or upload a PPTX or legacy PPT file.",
  pptxUpload: "Upload PowerPoint",
  pptxNoSlides: "This presentation has no slides.",
  slide: "Slide",
  slideLabel: ({ slide }) => `Slide ${slide}`,
  slideTotal: ({ total }) => `of ${total}`,
  slideNumber: "Slide number",
  currentSlide: ({ slide }) => `Current slide ${slide}. Edit slide number`,
  previousSlide: "Previous slide",
  nextSlide: "Next slide",
  slidesRegion: "PowerPoint slides",
  presentationRegion: "PowerPoint presentation",
  openPresentationActions: "Open PowerPoint actions",
  csvParseError: "Could not parse CSV file.",
  csvReadError: "Could not read CSV file.",
  csvEmptyTitle: "Upload a CSV to preview",
  csvEmptyDescription:
    "Pass delimited text with the data prop or upload a CSV file.",
  csvUpload: "Upload CSV",
  columnName: ({ index }) => `Column ${index}`,
  extraColumnName: ({ index }) => `Extra ${index}`,
  openCsvActions: "Open CSV actions",
}

const ViewerLabelsContext = React.createContext<ViewerLabels>(
  DEFAULT_VIEWER_LABELS
)

type ViewerTranslate = (
  key: string,
  values?: Record<string, string | number>
) => string

export function createViewerLabels(t: ViewerTranslate): ViewerLabels {
  return {
    ...DEFAULT_VIEWER_LABELS,
    loading: t("loading"),
    download: t("download"),
    upload: t("upload"),
    darkMode: t("darkMode"),
    zoomIn: t("zoomIn"),
    zoomOut: t("zoomOut"),
    zoomLevel: t("zoomLevel"),
    zoom: t("zoom"),
    fitPage: t("fitPage"),
    fitWidth: t("fitWidth"),
    automatic: t("automatic"),
    searchText: t("searchText"),
    searchWorkbook: t("searchWorkbook"),
    searchCsv: t("searchCsv"),
    searching: t("searching"),
    noSearch: t("noSearch"),
    noResults: t("noResults"),
    previousResult: t("previousResult"),
    nextResult: t("nextResult"),
    clear: t("clear"),
    page: t("page"),
    pageNumber: t("pageNumber"),
    currentPage: ({ page }) => t("currentPage", { page }),
    pageTotal: ({ total }) => t("pageTotal", { total }),
    pageLabel: ({ page }) => t("pageLabel", { page }),
    pagesSidebar: t("pagesSidebar"),
    toggleThumbnails: t("toggleThumbnails"),
    rotateCounterclockwise: t("rotateCounterclockwise"),
    rotateClockwise: t("rotateClockwise"),
    pagesRegion: t("pagesRegion"),
    openPdfActions: t("openPdfActions"),
    pdfLoadError: t("pdfLoadError"),
    pdfEngineLoadError: t("pdfEngineLoadError"),
    pdfEmptyTitle: t("pdfEmptyTitle"),
    pdfEmptyDescription: t("pdfEmptyDescription"),
    docxLoadError: t("docxLoadError"),
    docxLoadErrorTitle: t("docxLoadErrorTitle"),
    docxEmptyTitle: t("docxEmptyTitle"),
    docxEmptyDescription: t("docxEmptyDescription"),
    docxEmptyLegacy: t("docxEmptyLegacy"),
    docxUpload: t("docxUpload"),
    docxPages: t("docxPages"),
    docxDocumentRegion: t("docxDocumentRegion"),
    comments: t("comments"),
    edits: t("edits"),
    inserted: t("inserted"),
    removed: t("removed"),
    movedFrom: t("movedFrom"),
    movedTo: t("movedTo"),
    resolved: t("resolved"),
    reply: t("reply"),
    comment: t("comment"),
    unknownAuthor: t("unknownAuthor"),
    openDocxActions: t("openDocxActions"),
    xlsxLoadError: t("xlsxLoadError"),
    xlsxEmptyTitle: t("xlsxEmptyTitle"),
    xlsxEmptyDescription: t("xlsxEmptyDescription"),
    xlsxUpload: t("xlsxUpload"),
    xlsxTooLargeTitle: t("xlsxTooLargeTitle"),
    xlsxTooLargeDescription: t("xlsxTooLargeDescription"),
    openWorkbookActions: t("openWorkbookActions"),
    columnMenu: t("columnMenu"),
    sortAscending: t("sortAscending"),
    sortDescending: t("sortDescending"),
    xlsxActions: {
      cut: t("xlsxActions.cut"),
      copy: t("xlsxActions.copy"),
      paste: t("xlsxActions.paste"),
      clearContents: t("xlsxActions.clearContents"),
      editCell: t("xlsxActions.editCell"),
      undo: t("xlsxActions.undo"),
      redo: t("xlsxActions.redo"),
      mergeCells: t("xlsxActions.mergeCells"),
      mergeAndCenter: t("xlsxActions.mergeAndCenter"),
      mergeAcross: t("xlsxActions.mergeAcross"),
      unmergeCells: t("xlsxActions.unmergeCells"),
      sortAscending: t("xlsxActions.sortAscending"),
      sortDescending: t("xlsxActions.sortDescending"),
      selectRow: t("xlsxActions.selectRow"),
      selectColumn: t("xlsxActions.selectColumn"),
      selectAll: t("xlsxActions.selectAll"),
    },
    sheetPreview: ({ name }) => t("sheetPreview", { name }),
    pptxLoadError: t("pptxLoadError"),
    pptxEmptyTitle: t("pptxEmptyTitle"),
    pptxEmptyDescription: t("pptxEmptyDescription"),
    pptxUpload: t("pptxUpload"),
    pptxNoSlides: t("pptxNoSlides"),
    slide: t("slide"),
    slideLabel: ({ slide }) => t("slideLabel", { slide }),
    slideTotal: ({ total }) => t("slideTotal", { total }),
    slideNumber: t("slideNumber"),
    currentSlide: ({ slide }) => t("currentSlide", { slide }),
    previousSlide: t("previousSlide"),
    nextSlide: t("nextSlide"),
    slidesRegion: t("slidesRegion"),
    presentationRegion: t("presentationRegion"),
    openPresentationActions: t("openPresentationActions"),
    csvParseError: t("csvParseError"),
    csvReadError: t("csvReadError"),
    csvEmptyTitle: t("csvEmptyTitle"),
    csvEmptyDescription: t("csvEmptyDescription"),
    csvUpload: t("csvUpload"),
    columnName: ({ index }) => t("columnName", { index }),
    extraColumnName: ({ index }) => t("extraColumnName", { index }),
    openCsvActions: t("openCsvActions"),
  }
}

export function ViewerI18nProvider({
  children,
  labels,
}: {
  children: React.ReactNode
  labels: ViewerLabels
}) {
  return (
    <ViewerLabelsContext.Provider value={labels}>
      {children}
    </ViewerLabelsContext.Provider>
  )
}

export function useViewerLabels() {
  return React.useContext(ViewerLabelsContext)
}
