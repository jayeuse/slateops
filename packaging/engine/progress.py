"""Progress lines on standard error (TASK-0097 W14-D5: show what is being done).

Each engine job that can take more than a few seconds writes one line to its standard error
when a step starts. The Windows ``Exec`` job copies standard error to a file as it runs, so
the wizard can show the current step. Format, one line, ASCII, fields split by one space:

    progress <job> <number>/<total> <key> <state>

- ``<job>``: a key of ``STEPS``. ``update`` also writes ``rollback`` and ``recover`` lines when
  it closes a failed update (and the tick does when it closes an interrupted one).
- ``<number>/<total>``: the step's place in its job's list and the list's length.
- ``<key>``: the step's fixed name from ``STEPS``.
- ``<state>``: ``start`` when the step starts; ``done`` for a step that an earlier run of the
  same job finished and this run skips (only ``install`` resumes that way).

A step that does not run (a renewal that needs no reload, a check that waits for Docker)
writes no line, so a job can end before ``<total>``. No line holds a value from the input, a
path or a secret; each line also passes the job's redactor. A closed or broken standard error
never fails the job.
"""

from __future__ import annotations

from engine.context import Context

STEPS: dict[str, tuple[str, ...]] = {
    "receive": ("space", "stage", "signature", "check", "load", "keep"),
    "prepare": (
        "systemd", "docker", "container", "networking", "time", "listeners", "interop",
        "mounts", "shells", "bundle",
    ),
    # The pull runs in a worker unit; its numbers are in ``status`` (``prefetch``, ``progress``).
    "prefetch": ("start_pull",),
    "install": (
        "release", "folders", "images", "secrets", "env", "tls", "providers", "provision",
        "api", "caddy", "admin", "backup", "finish",
    ),
    "update": (
        "lock", "release", "space", "images", "backup", "env", "providers", "health",
        "provision", "api", "caddy", "switch",
    ),
    "recover": ("recover",),
    "rollback": ("down", "restore", "rebind", "finalize", "start", "adopt"),
    "smtp-test": ("send", "stage"),
    "set-email": ("write", "auth"),
    "set-backup-target": ("unmount", "mount", "repository"),
    "new-recovery-key": ("mount", "key"),
    "log-bundle": ("facts", "snapshot", "bundle"),
    "prepare-uninstall": ("stop_timer", "stop_docker"),
    "resend-invitation": ("resend",),
    "renew-certificate": ("renew", "check", "trust", "reload"),
}  # fmt: skip
STATES = ("start", "done")


def line(job: str, key: str, state: str = "start") -> str:
    """The progress line of ``key``; an unknown job, key or state is a programming error."""
    keys = STEPS[job]
    if state not in STATES:
        raise ValueError(f"progress state {state!r}")
    return f"progress {job} {keys.index(key) + 1}/{len(keys)} {key} {state}"


def report(ctx: Context, key: str, *, job: str | None = None, state: str = "start") -> None:
    text = line(job or ctx.job, key, state)
    if ctx.progress is None:
        return
    try:
        ctx.progress.write(ctx.redactor(text) + "\n")
        ctx.progress.flush()
    except (OSError, ValueError):  # a closed standard error must not fail the job
        pass
