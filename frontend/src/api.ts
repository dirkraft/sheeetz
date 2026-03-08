const BASE_URL = '/api'

export async function apiFetch<T = unknown>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE_URL}${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!resp.ok) {
    throw new Error(`API ${resp.status}: ${resp.statusText}`)
  }
  if (resp.status === 204) return undefined as T
  return resp.json()
}

export async function getMe() {
  return apiFetch<{ id: number; email: string; name: string }>('/auth/me')
}

// --- Settings ---

export interface UserSettings {
  columns: string[]
  organizeTemplate?: string
}

export async function getSettings() {
  return apiFetch<UserSettings>('/auth/settings')
}

export async function updateSettings(settings: Partial<UserSettings>) {
  return apiFetch<UserSettings>('/auth/settings', {
    method: 'PATCH',
    body: JSON.stringify(settings),
  })
}

// --- Sheet types ---

export interface SheetRecord {
  id: number
  filename: string
  folder_path: string | null
  backend_type: BackendType
  backend_file_id: string
  library_folder_id: number | null
  metadata: Record<string, string>
}

export interface SheetListResult {
  sheets: SheetRecord[]
  total: number
  page: number
  page_size: number
}

export interface SheetListParams {
  search?: string
  filename?: string
  folder_id?: number
  meta_key?: string
  meta_value?: string
  meta_filters?: Record<string, string>
  sort_by?: string
  sort_dir?: 'asc' | 'desc'
  page?: number
  page_size?: number
}

export async function getSheet(sheetId: number) {
  return apiFetch<SheetRecord>(`/sheets/${sheetId}`)
}

export async function getSheetPDF(sheetId: number): Promise<ArrayBuffer> {
  const resp = await fetch(`${BASE_URL}/sheets/${sheetId}/pdf`, {
    credentials: 'include',
  })
  if (!resp.ok) throw new Error(`API ${resp.status}: ${resp.statusText}`)
  return resp.arrayBuffer()
}

export async function getSheets(params: SheetListParams = {}) {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null) continue
    if (k === 'meta_filters') {
      qs.set(k, JSON.stringify(v))
    } else {
      qs.set(k, String(v))
    }
  }
  const suffix = qs.toString() ? `?${qs}` : ''
  return apiFetch<SheetListResult>(`/sheets${suffix}`)
}

export interface PdfMetadataResult {
  sheet_id: number
  filename: string
  metadata: Record<string, string>
}

export async function getPdfMetadata(sheetId: number) {
  return apiFetch<PdfMetadataResult>(`/sheets/${sheetId}/pdf-metadata`)
}

export interface MetadataUpdateResult {
  id: number
  metadata: Record<string, string>
}

export async function getMetadataKeys(query?: string) {
  const qs = new URLSearchParams()
  if (query) qs.set('q', query)
  return apiFetch<{ keys: string[] }>(`/sheets/metadata/keys?${qs}`)
}

export async function getMetadataValues(key: string, query?: string) {
  const qs = new URLSearchParams({ key })
  if (query) qs.set('q', query)
  return apiFetch<{ values: string[] }>(`/sheets/metadata/distinct?${qs}`)
}

export async function updateSheetMetadata(sheetId: number, metadata: Record<string, string>) {
  return apiFetch<MetadataUpdateResult>(`/sheets/${sheetId}/metadata`, {
    method: 'PATCH',
    body: JSON.stringify(metadata),
  })
}

// --- Scan ---

export interface ScanStatus {
  folder_id: number
  status: 'idle' | 'scanning' | 'complete' | 'error'
  current_file?: string
  processed?: number
  new_count?: number
  skipped_count?: number
  total_count?: number
  error?: string
}

export async function scanFolder(folderId: number) {
  return apiFetch<ScanStatus>(`/folders/${folderId}/scan`, { method: 'POST' })
}

export async function getScanStatus(folderId: number) {
  return apiFetch<ScanStatus>(`/folders/${folderId}/scan-status`)
}

// --- Organize ---

export interface SheetPreview {
  sheet_id: number
  filename: string
  from_path: string
  to_path: string | null
  can_move: boolean
  warning?: string
}

export interface OrganizePreviewResult {
  previews: SheetPreview[]
}

export interface OrganizeJobStatus {
  job_id: string
  status: 'running' | 'complete' | 'error'
  total: number
  processed: number
  moved_count: number
  failed_count: number
  current_file: string
  errors: string[]
  error: string
}

export async function previewOrganize(sheetIds: number[], template: string) {
  return apiFetch<OrganizePreviewResult>('/organize/preview', {
    method: 'POST',
    body: JSON.stringify({ sheet_ids: sheetIds, template }),
  })
}

export async function startOrganize(sheetIds: number[], template: string) {
  return apiFetch<OrganizeJobStatus>('/organize', {
    method: 'POST',
    body: JSON.stringify({ sheet_ids: sheetIds, template }),
  })
}

export async function getOrganizeJob(jobId: string) {
  return apiFetch<OrganizeJobStatus>(`/organize/jobs/${jobId}`)
}

// --- Admin ---

export async function clearIndex() {
  return apiFetch<{ deleted: number }>('/admin/clear-index', { method: 'POST' })
}

// --- Config ---

export async function getConfig() {
  return apiFetch<{ backends: BackendType[] }>('/config')
}

// --- Folder types ---

export type BackendType = 'local' | 'gdrive'

export interface BrowseFolder {
  id: string
  name: string
}

export interface FolderParent {
  id: string
  name: string
  parent_id: string | null
}

export interface LibraryFolder {
  id: number
  backend_type: BackendType
  backend_folder_id: string
  folder_name: string
  folder_path: string
}

// --- Folder API ---

export async function browseFolders(backend: BackendType, parentId = '') {
  const params = new URLSearchParams({ backend })
  if (parentId) params.set('parent_id', parentId)
  return apiFetch<{ folders: BrowseFolder[]; parent: FolderParent | null }>(
    `/folders/browse?${params}`
  )
}

export async function getSelectedFolders() {
  return apiFetch<{ folders: LibraryFolder[] }>('/folders')
}

export async function addFolder(backendType: BackendType, backendFolderId: string, folderName: string) {
  return apiFetch<LibraryFolder>('/folders', {
    method: 'POST',
    body: JSON.stringify({
      backend_type: backendType,
      backend_folder_id: backendFolderId,
      folder_name: folderName,
    }),
  })
}

export async function removeFolder(folderId: number) {
  return apiFetch<void>(`/folders/${folderId}`, { method: 'DELETE' })
}
