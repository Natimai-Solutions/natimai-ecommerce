/**
 * Phosphor (graisse « light ») comme famille d'icônes unique de la vitrine.
 *
 * Quasar et les pages désignent encore les icônes par leur nom Material
 * (`shopping_cart`, `chevron_left`…). Plutôt que de charger la police
 * Material Icons, ces noms sont traduits ici vers le glyphe Phosphor
 * équivalent. Le nouveau code peut viser Phosphor directement avec le préfixe
 * `ph:` (`icon="ph:magnifying-glass"`).
 */

export const MATERIAL_TO_PHOSPHOR: Readonly<Record<string, string>> = {
  // Jeu d'icônes interne de Quasar (material-icons)
  access_time: 'clock',
  add: 'plus',
  add_box: 'plus-square',
  arrow_back: 'arrow-left',
  arrow_downward: 'arrow-down',
  arrow_drop_down: 'caret-down',
  arrow_forward: 'arrow-right',
  arrow_upward: 'arrow-up',
  cancel: 'x-circle',
  check: 'check',
  check_circle: 'check-circle',
  chevron_left: 'caret-left',
  chevron_right: 'caret-right',
  clear: 'x',
  clear_all: 'x',
  close: 'x',
  cloud_upload: 'cloud-arrow-up',
  done: 'check',
  done_all: 'checks',
  edit: 'pencil-simple',
  error: 'warning-circle',
  first_page: 'caret-double-left',
  grade: 'star',
  info: 'info',
  keyboard_arrow_down: 'caret-down',
  keyboard_arrow_left: 'caret-left',
  keyboard_arrow_right: 'caret-right',
  keyboard_arrow_up: 'caret-up',
  last_page: 'caret-double-right',
  lens: 'circle',
  play_arrow: 'caret-right',
  priority_high: 'warning-circle',
  refresh: 'arrow-clockwise',
  today: 'calendar-blank',
  warning: 'warning',

  // Vitrine
  account_balance: 'bank',
  add_shopping_cart: 'shopping-bag',
  attach_file: 'paperclip',
  block: 'prohibit',
  credit_card: 'credit-card',
  delete: 'trash',
  delete_outline: 'trash',
  delete_sweep: 'broom',
  description: 'file-text',
  directions_boat: 'boat',
  error_outline: 'warning-circle',
  event: 'calendar-blank',
  filter_alt_off: 'funnel-x',
  flight: 'airplane',
  gavel: 'gavel',
  grid_view: 'squares-four',
  image_not_supported: 'image-broken',
  info_outline: 'info',
  inventory: 'package',
  inventory_2: 'package',
  local_shipping: 'truck',
  location_off: 'map-pin',
  location_on: 'map-pin',
  lock: 'lock',
  login: 'sign-in',
  logout: 'sign-out',
  mail: 'envelope-simple',
  mark_email_read: 'envelope-simple-open',
  menu: 'list',
  open_in_new: 'arrow-square-out',
  payments: 'money',
  person: 'user',
  picture_as_pdf: 'file-pdf',
  pin: 'push-pin',
  place: 'map-pin',
  receipt_long: 'receipt',
  remove: 'minus',
  report: 'warning-octagon',
  remove_shopping_cart: 'shopping-bag',
  route: 'path',
  save: 'floppy-disk',
  schedule: 'clock',
  search: 'magnifying-glass',
  search_off: 'magnifying-glass-minus',
  shopping_cart: 'shopping-bag',
  shopping_cart_checkout: 'shopping-bag',
  store: 'storefront',
  storefront: 'storefront',
  task_alt: 'check-circle',
  tune: 'sliders-horizontal',
  undo: 'arrow-counter-clockwise',
  upload_file: 'file-arrow-up',
  verified: 'seal-check',
  visibility: 'eye',
  visibility_off: 'eye-slash',
  warning_amber: 'warning',
  window: 'windows-logo',
  workspace_premium: 'seal-check',
  event_available: 'calendar-check',
  history: 'clock-counter-clockwise',
  link: 'link',
  request_quote: 'receipt',
  savings: 'piggy-bank',
  notifications_active: 'bell-ringing',
  publish: 'upload-simple',
};

const FALLBACK = 'question';
const warned = new Set<string>();

/** Nom Phosphor pour un nom d'icône Quasar/Material ou `ph:<nom>`. */
export function resolvePhosphorName(iconName: string): string | null {
  if (iconName.startsWith('ph:')) return iconName.slice(3);
  return MATERIAL_TO_PHOSPHOR[iconName] ?? null;
}

/**
 * `$q.iconMapFn` : laisse passer les formes gérées nativement par Quasar
 * (`img:`, `svguse:`…) et traduit tout le reste vers une classe Phosphor.
 */
export function phosphorIconMapFn(iconName: string): { cls: string } | undefined {
  if (/^(img:|svguse:)/.test(iconName) || /^[Mm][\d.-]/.test(iconName)) return undefined;
  let name = resolvePhosphorName(iconName);
  if (name === null) {
    if (process.env.DEV && !warned.has(iconName)) {
      warned.add(iconName);
      console.warn(
        `[icons] « ${iconName} » n'a pas d'équivalent Phosphor, ajoutez-le à MATERIAL_TO_PHOSPHOR.`,
      );
    }
    name = FALLBACK;
  }
  return { cls: `ph-light ph-${name}` };
}
