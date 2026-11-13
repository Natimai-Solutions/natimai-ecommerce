import { nextTick, onBeforeUnmount, watch, type Ref } from 'vue';

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), ' +
  'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * A panel shown over the page (the catalogue's mobile filters) behaves as a
 * modal dialog (audit 2026-11, U6): focus moves in and stays in (Tab
 * cycles), Escape closes it, the page behind does not scroll, and focus
 * returns to the button that opened it. Mark the panel `role="dialog"` and
 * `aria-modal="true"` while `open` is true.
 */
export function useModalSheet(
  open: Ref<boolean>,
  panel: Ref<HTMLElement | null>,
  opener: Ref<{ $el?: HTMLElement } | HTMLElement | null>,
): void {
  function focusables(): HTMLElement[] {
    const root = panel.value;
    if (!root) return [];
    return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
      (el) => el.offsetParent !== null || el === document.activeElement,
    );
  }

  function onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Escape') {
      event.preventDefault();
      open.value = false;
      return;
    }
    if (event.key !== 'Tab') return;
    const items = focusables();
    if (items.length === 0) return;
    const first = items[0]!;
    const last = items[items.length - 1]!;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function openerElement(): HTMLElement | null {
    const value = opener.value;
    if (!value) return null;
    return value instanceof HTMLElement ? value : (value.$el ?? null);
  }

  function release(): void {
    document.removeEventListener('keydown', onKeydown);
    document.body.style.removeProperty('overflow');
  }

  watch(open, async (isOpen) => {
    if (typeof document === 'undefined') return;
    if (isOpen) {
      document.addEventListener('keydown', onKeydown);
      document.body.style.overflow = 'hidden';
      await nextTick();
      focusables()[0]?.focus();
    } else {
      release();
      openerElement()?.focus();
    }
  });

  onBeforeUnmount(() => {
    if (typeof document !== 'undefined') release();
  });
}
