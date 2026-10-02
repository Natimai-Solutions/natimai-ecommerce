import { execFileSync } from 'node:child_process'

/**
 * Peeking into the stack under test (R8 / U10).
 *
 * The sign-up code and the password-reset link leave the API by e-mail; the
 * CI stack has no mailbox (the `noop` provider), so the journeys read them
 * where the API puts them: the code in Redis (`otp:<email>`), the link in the
 * API log, which prints it in the `local` environment only. Both go through
 * `docker compose`, the way the stack is started (e2e/README.md); without
 * Docker at hand the journeys that need them are skipped, not failed.
 */
const COMPOSE_FILE = process.env.E2E_COMPOSE_FILE ?? 'docker-compose.yml'

function compose(args: string[], timeoutMs = 30_000): string {
  return execFileSync('docker', ['compose', '-f', COMPOSE_FILE, ...args], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'ignore'],
    timeout: timeoutMs,
    cwd: process.env.E2E_COMPOSE_CWD ?? '..',
  })
}

/** True when the compose stack answers from here (Docker installed, stack up). */
export function stackReachable(): boolean {
  try {
    return compose(['ps', '--services', '--status', 'running']).includes('redis')
  } catch {
    return false
  }
}

/** The 6-digit sign-up code the API stored for `email` (null when none yet). */
export function readSignupOtp(email: string): string | null {
  try {
    const raw = compose([
      'exec',
      '-T',
      'redis',
      'redis-cli',
      '--raw',
      'GET',
      `otp:${email.toLowerCase()}`,
    ]).trim()
    if (!raw) return null
    const parsed = JSON.parse(raw) as { code?: unknown }
    return typeof parsed.code === 'string' ? parsed.code : null
  } catch {
    return null
  }
}

/** The last password-reset link the API logged for `email` (local env only). */
export function readPasswordResetLink(email: string): string | null {
  try {
    const logs = compose(['logs', '--no-color', '--no-log-prefix', '--tail', '2000', 'api'])
    const needle = `password reset link for ${email.toLowerCase()} = `
    const lines = logs.split('\n').filter((line) => line.includes(needle))
    const last = lines[lines.length - 1]
    if (!last) return null
    const match = /(https?:\/\/\S+)/.exec(last.slice(last.indexOf(needle) + needle.length))
    return match?.[1] ?? null
  } catch {
    return null
  }
}

/** Poll a reader until it answers, for the few seconds the e-mail path takes. */
export async function waitFor<T>(
  read: () => T | null,
  { attempts = 20, delayMs = 500 } = {},
): Promise<T> {
  for (let i = 0; i < attempts; i += 1) {
    const value = read()
    if (value !== null) return value
    await new Promise((resolve) => setTimeout(resolve, delayMs))
  }
  throw new Error('nothing to read from the stack in time')
}
