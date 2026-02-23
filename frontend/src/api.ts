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

export async function getSheets() {
  return apiFetch<{ sheets: unknown[]; total: number }>('/sheets')
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
