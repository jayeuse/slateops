"use client";

import { useServerUnreachable } from "@/components/server-connection-banner";
import { backupPauseExpected } from "@/lib/backup-pause";

/** Owner item 4 (rc.35 round): the server does not answer because this tab's backup runs,
 * so the Backup page waits instead of showing a failure. */
export function useBackupPause(): boolean {
  const unreachable = useServerUnreachable();
  return unreachable && backupPauseExpected();
}
