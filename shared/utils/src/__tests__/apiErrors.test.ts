import { describe, expect, it } from "vitest";

import { API_ERROR_CODES, apiErrorText, fillPlaceholders } from "../apiErrors";

describe("API error texts", () => {
  it("translates a code in the interface language", () => {
    expect(apiErrorText("cart.empty", {}, "fr")).toBe("Votre panier est vide.");
    expect(apiErrorText("cart.empty", {}, "en-GB")).toBe("Your cart is empty.");
  });

  it("fills the placeholders from the details", () => {
    expect(
      apiErrorText(
        "cart.stock.insufficient",
        { product_name: "Écran", available: 2 },
        "fr",
      ),
    ).toBe(
      "« Écran » : il n’en reste que 2. Ajustez la quantité pour continuer.".replace(
        "’",
        "'",
      ),
    );
  });

  it("leaves the server fallback when it cannot say it right", () => {
    expect(apiErrorText("not.catalogued", {}, "fr")).toBeNull();
    // A placeholder without its value: no text with a hole.
    expect(apiErrorText("cart.stock.insufficient", {}, "fr")).toBeNull();
    expect(apiErrorText(null, {}, "fr")).toBeNull();
  });

  it("falls back on French for a language without catalogue", () => {
    expect(apiErrorText("cart.empty", {}, "ty")).toBe("Votre panier est vide.");
  });

  it("keeps an unknown placeholder as is", () => {
    expect(fillPlaceholders("{a} and {b}", { a: 1 })).toBe("1 and {b}");
  });

  it("catalogues the codes the frontends handle themselves", () => {
    for (const code of [
      "cart.price.changed",
      "cart.already_checked_out",
      "cart.stock.insufficient",
    ]) {
      expect(API_ERROR_CODES).toContain(code);
    }
  });
});
