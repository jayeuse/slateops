// Owner item 4 (rc.35 round): a backup is an offline copy, so the server stops for about a
// minute while it runs. The tab that queued the backup remembers when, so the shell and the
// Backup page can say why the server does not answer instead of reporting a failure.

const KEY = "slateops.backup-queued-at";
// The runner claims a queued backup within a minute, and the copy itself takes a few minutes.
export const BACKUP_PAUSE_MILLISECONDS = 15 * 60 * 1000;

export function markBackupQueued(now: number = Date.now()): void {
  try {
    sessionStorage.setItem(KEY, String(now));
  } catch {
    // Without storage the page shows the plain server message.
  }
}

/** Whether a backup queued at `queued` (milliseconds, or none) explains a silent server now. */
export function backupPauseCovers(queued: number | null, now: number): boolean {
  return (
    queued !== null &&
    queued > 0 &&
    now >= queued &&
    now - queued < BACKUP_PAUSE_MILLISECONDS
  );
}

/** Whether this tab queued a backup recently enough that a silent server is the backup. */
export function backupPauseExpected(now: number = Date.now()): boolean {
  try {
    const stored = sessionStorage.getItem(KEY);
    return backupPauseCovers(stored === null ? null : Number(stored), now);
  } catch {
    return false;
  }
}
