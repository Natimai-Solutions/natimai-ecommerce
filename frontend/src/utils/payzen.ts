/** PayZen SmartForm loader, shared by the checkout and the balance payment. */

/** localStorage key of the payment being polled by the return page. */
export const PENDING_PAYMENT_KEY = 'payzen.pending_payment_id';

export interface SmartFormOptions {
  serverUrl: string;
  publicKey: string;
  token: string;
  returnUrl: string;
  /** Interface language (`fr`, `en`…): the form follows it. */
  language?: string;
}

/** PayZen expects a full tag (`fr-FR`, `en-GB`…). */
export function payzenLanguage(locale: string | undefined): string {
  const base = (locale ?? 'fr').toLowerCase().split('-')[0] || 'fr';
  return base === 'en' ? 'en-GB' : base === 'fr' ? 'fr-FR' : `${base}-${base.toUpperCase()}`;
}

/** Load the PayZen script and render the form into `#kr-smart-form-container`. */
export function loadPayzenSmartForm({
  serverUrl,
  publicKey,
  token,
  returnUrl,
  language,
}: SmartFormOptions): Promise<void> {
  return new Promise((resolve, reject) => {
    const existing = document.getElementById('kr-payzen-script');
    if (existing) existing.remove();

    const script = document.createElement('script');
    script.id = 'kr-payzen-script';
    script.src = `${serverUrl}/static/js/krypton-client/V4.0/ext/smartform.min.js`;
    script.setAttribute('kr-public-key', publicKey);
    script.setAttribute('kr-post-url-success', returnUrl);
    script.setAttribute('kr-language', payzenLanguage(language));
    script.onload = () => {
      const container = document.getElementById('kr-smart-form-container');
      if (container) {
        container.innerHTML = `<div class="kr-smart-form" kr-form-token="${token}"></div>`;
      }
      resolve();
    };
    script.onerror = () => reject(new Error('Impossible de charger le script Payzen'));
    document.head.appendChild(script);
  });
}
