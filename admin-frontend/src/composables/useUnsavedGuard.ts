import { useQuasar } from 'quasar';
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { onBeforeRouteLeave } from 'vue-router';

/**
 * « Modifications non enregistrées » (R9 / T5): while `isDirty()` is true,
 * leaving the screen (route change) asks for confirmation and closing or
 * reloading the tab shows the browser's own prompt.
 *
 * Call it from a page, or from a component rendered inside a page (a dialog):
 * the route guard attaches to the current route either way.
 */
export function useUnsavedGuard(isDirty: () => boolean) {
  const $q = useQuasar();
  const { t } = useI18n();

  /** Resolves true when leaving is fine (clean, or the user confirmed). */
  function confirmLeave(): Promise<boolean> {
    if (!isDirty()) return Promise.resolve(true);
    return new Promise((resolve) => {
      $q.dialog({
        title: t('common.unsaved_title'),
        message: t('common.unsaved_message'),
        persistent: true,
        ok: { label: t('common.unsaved_leave'), color: 'negative', flat: true, noCaps: true },
        cancel: { label: t('common.unsaved_stay'), flat: true, noCaps: true },
      })
        .onOk(() => resolve(true))
        .onCancel(() => resolve(false))
        .onDismiss(() => resolve(false));
    });
  }

  onBeforeRouteLeave(() => confirmLeave());

  function onBeforeUnload(event: BeforeUnloadEvent) {
    if (!isDirty()) return;
    event.preventDefault();
    // Legacy browsers read the returned value; modern ones show their own text.
    event.returnValue = '';
  }
  onMounted(() => window.addEventListener('beforeunload', onBeforeUnload));
  onBeforeUnmount(() => window.removeEventListener('beforeunload', onBeforeUnload));

  return { confirmLeave };
}

/**
 * The same guard for a dialog: `requestClose()` asks before closing a dirty
 * form, `onToggle` is the handler for the dialog's `update:model-value`, and
 * `persistent` keeps a dirty dialog from closing on Escape or a backdrop click.
 */
export function useDialogGuard(options: {
  isOpen: () => boolean;
  close: () => void;
  isDirty: () => boolean;
}) {
  const dirty = () => options.isOpen() && options.isDirty();
  const { confirmLeave } = useUnsavedGuard(dirty);

  async function requestClose(): Promise<void> {
    if (await confirmLeave()) options.close();
  }

  function onToggle(value: boolean): void {
    if (!value) void requestClose();
  }

  const persistent = computed(dirty);
  return { requestClose, onToggle, persistent, confirmLeave };
}

/**
 * Dirty tracking by snapshot: `take()` when the form is (re)filled, `isDirty()`
 * compares the serialised form with that snapshot.
 */
export function useFormSnapshot(source: () => unknown) {
  const snapshot = ref<string | null>(null);
  function take(): void {
    snapshot.value = JSON.stringify(source());
  }
  function isDirty(): boolean {
    return snapshot.value !== null && JSON.stringify(source()) !== snapshot.value;
  }
  return { take, isDirty };
}
