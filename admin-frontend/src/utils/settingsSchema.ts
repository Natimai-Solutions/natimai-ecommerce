/**
 * Champs d'un formulaire construits depuis un schéma JSON Pydantic (R5 / C4) :
 * les réglages propres à un fournisseur (`Supplier.settings`) sont décrits par
 * l'intégration elle-même, l'admin n'a plus de liste de clés en dur.
 *
 * Le formulaire garde chaque valeur en texte ; `fromFormValue` la retype avant
 * l'envoi (liste, nombre, JSON). Une valeur vide est omise : l'environnement
 * (ou le défaut) s'applique.
 */

export type SchemaFieldKind = 'text' | 'choice' | 'list' | 'number' | 'json';

export interface SchemaField {
  key: string;
  label: string;
  hint: string;
  kind: SchemaFieldKind;
  choices?: string[];
}

interface JsonSchemaNode {
  type?: string;
  enum?: unknown[];
  anyOf?: JsonSchemaNode[];
  items?: JsonSchemaNode;
  $ref?: string;
  title?: string;
  description?: string;
}

interface JsonSchemaObject {
  properties?: Record<string, JsonSchemaNode>;
}

/** Les variantes non nulles d'un `X | None` Pydantic. */
function variants(node: JsonSchemaNode): JsonSchemaNode[] {
  const list = node.anyOf ?? [node];
  return list.filter((v) => v.type !== 'null');
}

function kindOf(node: JsonSchemaNode): Pick<SchemaField, 'kind' | 'choices'> {
  const options = variants(node);
  const withEnum = options.find((v) => Array.isArray(v.enum));
  if (withEnum) return { kind: 'choice', choices: (withEnum.enum ?? []).map(String) };
  const array = options.find((v) => v.type === 'array');
  if (array) {
    const item = array.items ?? {};
    return item.type === 'string' ? { kind: 'list' } : { kind: 'json' };
  }
  if (options.some((v) => v.type === 'number' || v.type === 'integer')) return { kind: 'number' };
  if (options.some((v) => v.type === 'object' || v.$ref)) return { kind: 'json' };
  return { kind: 'text' };
}

export function fieldsFromSchema(
  schema: unknown,
  labels: Record<string, string> = {},
): SchemaField[] {
  const properties = (schema as JsonSchemaObject | null)?.properties ?? {};
  return Object.entries(properties).map(([key, node]) => ({
    key,
    label: labels[key] ?? node.title ?? key,
    hint: node.description ?? '',
    ...kindOf(node),
  }));
}

/** Valeur stockée → texte du formulaire. */
export function toFormValue(field: SchemaField | undefined, value: unknown): string {
  if (value === null || value === undefined) return '';
  if (field?.kind === 'list' && Array.isArray(value)) return value.map(String).join(', ');
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return JSON.stringify(value, null, 2);
}

/**
 * Texte du formulaire → valeur envoyée ; `undefined` : champ omis.
 * Lève une `Error` (message en français) sur un JSON illisible.
 */
export function fromFormValue(field: SchemaField | undefined, text: string): unknown {
  const raw = text.trim();
  if (!raw) return undefined;
  switch (field?.kind) {
    case 'list':
      // « [] » : liste vide explicite (tout est autorisé).
      if (raw === '[]') return [];
      return raw
        .split(/[,\n]/)
        .map((part) => part.trim())
        .filter(Boolean);
    case 'json':
      try {
        return JSON.parse(raw) as unknown;
      } catch {
        throw new Error(`${field.label} : JSON invalide`);
      }
    default:
      return raw;
  }
}
