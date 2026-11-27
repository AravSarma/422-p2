export interface OfficerSession {
  token: string;
  /**
   * Converts an error into a user-facing message. On 401 it also logs the
   * officer out and returns "" (the login screen shows its own notice).
   */
  handleError: (err: unknown) => string;
}
