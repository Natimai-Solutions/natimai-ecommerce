/**
 * Phosphor (graisse « light ») comme famille d'icônes unique de la vitrine et
 * de l'admin.
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
  code: 'code',
  done: 'check',
  done_all: 'checks',
  edit: 'pencil-simple',
  error: 'warning-circle',
  first_page: 'caret-double-left',
  font_download: 'text-aa',
  format_align_center: 'text-align-center',
  format_align_justify: 'text-align-justify',
  format_align_left: 'text-align-left',
  format_align_right: 'text-align-right',
  format_bold: 'text-b',
  format_clear: 'eraser',
  format_indent_decrease: 'text-outdent',
  format_indent_increase: 'text-indent',
  format_italic: 'text-italic',
  format_list_bulleted: 'list-bullets',
  format_list_numbered: 'list-numbers',
  format_quote: 'quotes',
  format_size: 'text-t',
  format_underlined: 'text-underline',
  fullscreen: 'arrows-out',
  grade: 'star',
  gradient: 'gradient',
  info: 'info',
  keyboard_arrow_down: 'caret-down',
  keyboard_arrow_left: 'caret-left',
  keyboard_arrow_right: 'caret-right',
  keyboard_arrow_up: 'caret-up',
  last_page: 'caret-double-right',
  lens: 'circle',
  play_arrow: 'caret-right',
  print: 'printer',
  priority_high: 'warning-circle',
  redo: 'arrow-clockwise',
  refresh: 'arrow-clockwise',
  strikethrough_s: 'text-strikethrough',
  style: 'paint-brush',
  text_format: 'text-aa',
  today: 'calendar-blank',
  vertical_align_bottom: 'align-bottom',
  vertical_align_top: 'align-top',
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

  // Admin
  add_photo_alternate: 'image',
  admin_panel_settings: 'shield-check',
  article: 'article',
  category: 'folders',
  chat: 'chat-circle',
  currency_exchange: 'arrows-left-right',
  download: 'download-simple',
  favorite: 'heart',
  forward_to_inbox: 'paper-plane-right',
  home: 'house',
  image: 'image',
  local_offer: 'tag',
  local_post_office: 'mailbox',
  merge: 'git-merge',
  monitor_heart: 'heartbeat',
  my_location: 'crosshair',
  people: 'users',
  percent: 'percent',
  person_add: 'user-plus',
  person_off: 'user-minus',
  photo_library: 'images',
  playlist_add_check: 'list-checks',
  price_check: 'check-square-offset',
  public: 'globe',
  record_voice_over: 'megaphone',
  replay: 'arrow-counter-clockwise',
  report_problem: 'warning',
  request_page: 'note-pencil',
  rss_feed: 'rss',
  school: 'graduation-cap',
  send: 'paper-plane-tilt',
  settings: 'gear',
  shield: 'shield',
  skip_next: 'skip-forward',
  star: 'star',
  star_outline: 'star',
  sync: 'arrows-clockwise',
  timeline: 'chart-line-up',
  title: 'text-h',
  warehouse: 'warehouse',
  webhook: 'webhooks-logo',
};

const FALLBACK = 'question';

/** Nom Phosphor pour un nom d'icône Quasar/Material ou `ph:<nom>`. */
export function resolvePhosphorName(iconName: string): string | null {
  if (iconName.startsWith('ph:')) return iconName.slice(3);
  return MATERIAL_TO_PHOSPHOR[iconName] ?? null;
}

/**
 * Fabrique le `$q.iconMapFn` : laisse passer les formes gérées nativement par
 * Quasar (`img:`, `svguse:`, tracés SVG) et traduit tout le reste vers une
 * classe Phosphor. `onMissing` est appelé une fois par nom inconnu (les apps
 * l'utilisent pour avertir en développement).
 */
export function createPhosphorIconMapFn(
  onMissing?: (iconName: string) => void,
): (iconName: string) => { cls: string } | undefined {
  const reported = new Set<string>();
  return (iconName) => {
    if (/^(img:|svguse:)/.test(iconName) || /^[Mm][\d.-]/.test(iconName)) return undefined;
    let name = resolvePhosphorName(iconName);
    if (name === null) {
      if (onMissing && !reported.has(iconName)) {
        reported.add(iconName);
        onMissing(iconName);
      }
      name = FALLBACK;
    }
    return { cls: `ph-light ph-${name}` };
  };
}

/** Variante sans avertissement (tests, rendu serveur). */
export const phosphorIconMapFn = createPhosphorIconMapFn();

export function warnMissingIcon(iconName: string): void {
  console.warn(
    `[icons] « ${iconName} » n'a pas d'équivalent Phosphor, ajoutez-le à MATERIAL_TO_PHOSPHOR (shared/ui).`,
  );
}
