import { useI18n } from 'vue-i18n';

import type { Translate } from '@/utils/availability';

/** `t` as a plain function, for the helpers that take a translator. */
export function useTranslate(): Translate {
  const { t } = useI18n();
  return (key, named) => t(key, named ?? {});
}
