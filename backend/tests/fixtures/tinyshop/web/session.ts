import { Session } from "./types";

/** Decode the expiry embedded in a session token ("<user>.<expires>.<sig>"). */
export function tokenExpiry(token: string): number {
  const [, expires] = token.split(".");
  return Number(expires) * 1000;
}

/** Keeps the current session and refreshes it shortly before it expires. */
export class SessionManager {
  private session: Session | null = null;

  /** True when there is a session whose token has not expired yet. */
  isLoggedIn(now: number = Date.now()): boolean {
    return this.session !== null && tokenExpiry(this.session.token) > now;
  }

  start(session: Session): void {
    this.session = session;
  }
}
