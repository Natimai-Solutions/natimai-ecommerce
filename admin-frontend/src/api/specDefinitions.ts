import { api } from 'src/boot/api'

export interface SpecDefinition {
  id: string
  key: string
  label_fr: string
  type: string
  unit: string | null
  categories: string[]
  aliases: string[]
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface SpecDefinitionCreate {
  key: string
  label_fr: string
  type: string
  unit?: string | null
  categories: string[]
  aliases: string[]
  is_active?: boolean
}

export type SpecDefinitionUpdate = Partial<Omit<SpecDefinitionCreate, 'key'>>

interface SpecDefinitionsResponse {
  data: SpecDefinition[]
  count: number
}

export async function listSpecDefinitions(): Promise<SpecDefinition[]> {
  const { data } = await api.get<SpecDefinitionsResponse>('/admin/spec-definitions')
  return data.data
}

export async function createSpecDefinition(
  payload: SpecDefinitionCreate,
): Promise<SpecDefinition> {
  const { data } = await api.post<SpecDefinition>('/admin/spec-definitions', payload)
  return data
}

export async function updateSpecDefinition(
  key: string,
  payload: SpecDefinitionUpdate,
): Promise<SpecDefinition> {
  const { data } = await api.put<SpecDefinition>(`/admin/spec-definitions/${key}`, payload)
  return data
}

/** Soft-delete (sets is_active=false server-side). */
export async function deleteSpecDefinition(key: string): Promise<void> {
  await api.delete(`/admin/spec-definitions/${key}`)
}
