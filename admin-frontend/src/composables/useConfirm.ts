import { useQuasar } from 'quasar';
import { useI18n } from 'vue-i18n';

/**
 * The one confirmation dialog of the back-office (R9 / T8): same title, same
 * wording, cancel on the left, the destructive action on the right in red.
 * Resolves true when the user confirmed.
 */
export function useConfirm() {
  const $q = useQuasar();
  const { t } = useI18n();

  function ask(options: {
    title: string;
    message?: string;
    okLabel?: string;
    destructive?: boolean;
  }): Promise<boolean> {
    return new Promise((resolve) => {
      $q.dialog({
        title: options.title,
        message: options.message ?? '',
        persistent: true,
        ok: {
          label: options.okLabel ?? t('common.confirm'),
          color: options.destructive === false ? 'primary' : 'negative',
          flat: true,
          noCaps: true,
        },
        cancel: { label: t('common.cancel'), flat: true, noCaps: true },
      })
        .onOk(() => resolve(true))
        .onCancel(() => resolve(false))
        .onDismiss(() => resolve(false));
    });
  }

  /** « Supprimer « {name} » ? » with the standard warning and a red « Supprimer ». */
  function confirmDelete(name: string, message?: string): Promise<boolean> {
    return ask({
      title: t('common.delete_q', { name }),
      message: message ?? t('common.delete_warning'),
      okLabel: t('common.delete'),
    });
  }

  /**
   * A confirmation that also takes a reason (kept in the order history).
   * Resolves to the reason typed (possibly empty), or null when cancelled.
   */
  function askWithReason(options: {
    title: string;
    message?: string;
    okLabel?: string;
    destructive?: boolean;
  }): Promise<string | null> {
    return new Promise((resolve) => {
      $q.dialog({
        title: options.title,
        message: options.message ?? '',
        persistent: true,
        prompt: { model: '', type: 'text', label: t('common.reason_optional') },
        ok: {
          label: options.okLabel ?? t('common.confirm'),
          color: options.destructive ? 'negative' : 'primary',
          flat: true,
          noCaps: true,
        },
        cancel: { label: t('common.cancel'), flat: true, noCaps: true },
      })
        .onOk((reason: string) => resolve(reason ?? ''))
        .onCancel(() => resolve(null))
        .onDismiss(() => resolve(null));
    });
  }

  return { ask, askWithReason, confirmDelete };
}
