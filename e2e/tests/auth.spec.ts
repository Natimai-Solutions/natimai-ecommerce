import { expect, test, type Page } from '@playwright/test'

import { STOREFRONT_URL } from '../support/env'
import { readPasswordResetLink, readSignupOtp, stackReachable, waitFor } from '../support/stack'

/**
 * The account journeys (R8 / U10): sign-up with the e-mailed code, sign-in
 * (wrong then right password), forgotten password and its reset link.
 *
 * Everything happens on a fresh account created by the first step, so the
 * seeded customer the other journeys rely on is never touched. The code and
 * the reset link are read from the stack (support/stack.ts); without Docker
 * the test is skipped.
 */
const EMAIL = `e2e-signup+${Date.now()}@example.com`
const PASSWORD = 'premier-mot-de-passe-123'
const NEW_PASSWORD = 'second-mot-de-passe-456'

async function gotoHydrated(page: Page, path: string) {
  await page.goto(path)
  await page.locator('html[data-hydrated]').waitFor({ state: 'attached' })
}

async function signIn(page: Page, email: string, password: string) {
  await gotoHydrated(page, '/connexion')
  await page.getByTestId('login-email').fill(email)
  await page.getByTestId('login-password').fill(password)
  await page.getByTestId('login-submit').click()
}

test('a visitor signs up with the e-mailed code, signs in and resets a forgotten password', async ({
  page,
}) => {
  test.skip(!stackReachable(), 'docker compose stack not reachable: cannot read the OTP')

  await test.step('sign-up: e-mail, code, password', async () => {
    await gotoHydrated(page, '/inscription')
    await page.getByTestId('register-email').fill(EMAIL)
    await page.getByTestId('register-send-code').click()
    await expect(page.getByTestId('register-code')).toBeVisible()

    const code = await waitFor(() => readSignupOtp(EMAIL))
    await page.getByTestId('register-code').fill(code)
    await page.getByTestId('register-verify-code').click()
    await expect(page.getByTestId('register-password')).toBeVisible()

    await page.getByTestId('register-name').fill('Client Inscription E2E')
    await page.getByTestId('register-password').fill(PASSWORD)
    await page.getByTestId('register-password-confirm').fill(PASSWORD)
    await page.getByTestId('register-submit').click()
    // Signing up signs in: the page leaves /inscription.
    await expect(page).not.toHaveURL(/inscription/)
    await gotoHydrated(page, '/mon-compte')
    await expect(page.getByTestId('account-nav-overview')).toBeVisible()
  })

  await test.step('sign out, then a wrong password is refused and the right one accepted', async () => {
    // A fresh context state: drop the session the way the layout's logout does.
    await page.request.post(`${STOREFRONT_URL.replace(':3000', ':8000')}/api/v1/login/logout`)
    await page.context().clearCookies()

    await signIn(page, EMAIL, 'pas-le-bon-mot-de-passe')
    await expect(page.getByText('Email ou mot de passe incorrect.')).toBeVisible()
    await expect(page).toHaveURL(/connexion/)

    await signIn(page, EMAIL, PASSWORD)
    await expect(page).not.toHaveURL(/connexion/)
    await page.context().clearCookies()
  })

  await test.step('forgotten password: the e-mailed link sets a new one', async () => {
    await gotoHydrated(page, '/mot-de-passe-oublie')
    await page.getByTestId('forgot-email').fill(EMAIL)
    await page.getByTestId('forgot-submit').click()
    await expect(page.getByTestId('forgot-submit')).toBeHidden()

    const link = await waitFor(() => readPasswordResetLink(EMAIL))
    const url = new URL(link)
    await gotoHydrated(page, `${url.pathname}${url.search}`)
    await page.getByTestId('reset-password').fill(NEW_PASSWORD)
    await page.getByTestId('reset-confirmation').fill(NEW_PASSWORD)
    await page.getByTestId('reset-submit').click()
    await expect(page.getByTestId('reset-submit')).toBeHidden()

    await signIn(page, EMAIL, 'pas-le-bon-mot-de-passe')
    await expect(page.getByText('Email ou mot de passe incorrect.')).toBeVisible()
    await signIn(page, EMAIL, NEW_PASSWORD)
    await expect(page).not.toHaveURL(/connexion/)
  })
})
