"""``renew-certificate``: keep the server certificate and the trust files current (plan 6.3,
W6a-4; TASK-0089). The ``tick`` of ``slateops-runner.timer`` runs it once a day after the
runner (TASK-0093); support can also run it. It never overlaps the backup runner: it refuses
with ``runner_busy`` while the runner's host lock is held, a ``slateops-runner`` container
exists or a runner journal is active (the runner owns Caddy's state until it resolves).

Steps, each safe to repeat after a kill:

0. Remove the staged leaf files that a killed renewal left in ``tls/`` (the backup refuses
   them, TASK-0092 N-4); ``local_ca.py`` writes them anew.

1. ``local_ca.py renew``: a new leaf only 30 days or less before the old one ends (W2), or
   when the leaf pair is missing.
2. ``local_ca.py check``: the chain, and the throwaway ``other.local`` leaf fails (F6).
3. The key owner and mode for Caddy, on every run (a kill after step 1 leaves a root-owned key).
4. The trust files (R6).
5. Caddy reload, decided by the state and not by step 1's answer: when Caddy serves another
   leaf than ``server.crt`` (a renewal now, or one that a kill left unloaded), the engine runs
   ``caddy reload --force`` in the Caddy container (a plain reload keeps a certificate whose
   files changed) and checks ``https://<host>/api/health`` with the installation's CA. A
   reload keeps the listeners open, so the outage is no longer than the reload (W6a-4).
   When Caddy does not answer, nothing is reloaded: it reads the files when it starts.
"""

from __future__ import annotations

import ssl
from typing import Any

from engine import answers, backups, compose, install, journal, trust
from engine.context import Context
from engine.core import failed, is_run_id, refused

KEYS = {"run_id": is_run_id}
REQUIRED = frozenset(KEYS)
STAGED = (".server.key.new", ".server.crt.new")  # local_ca.py install_leaf
RELOAD = ["caddy", "reload", "--force", "--config", "/etc/caddy/Caddyfile", "--adapter",
          "caddyfile"]  # fmt: skip


def _file_leaf(ctx: Context) -> bytes:
    text = (ctx.paths.etc / "tls" / "server.crt").read_text(encoding="ascii")
    end = "-----END CERTIFICATE-----"
    return ssl.PEM_cert_to_DER_cert(text[: text.index(end) + len(end)] + "\n")


def _served(ctx: Context, host: str) -> bytes | None:
    """The leaf that Caddy serves; ``b""`` when it fails verification against the root (for
    example expired after the PC was off through its last 30 days: B-1), which counts as
    another leaf and is reloaded; None only when Caddy does not answer."""
    root = ctx.paths.etc / "ca" / "current" / "root.crt"
    try:
        return ctx.deps.served_certificate(host, root, 10.0)
    except ssl.SSLCertVerificationError as error:
        ctx.log.line(
            ctx.step(5, "reload"), "WARN", f"served certificate fails verification: {error}"
        )
        return b""
    except (OSError, ssl.SSLError):
        return None


def _reload(ctx: Context, step: str, project: str, host: str) -> bool:
    served = _served(ctx, host)
    if served is None:
        ctx.log.line(step, "WARN", "Caddy does not answer; it reads the new files when it starts")
        return False
    if served == _file_leaf(ctx):
        ctx.log.line(step, "INFO", "Caddy serves the current certificate")
        return False
    reload = ctx.runner.run(step, compose.argv(ctx.paths, project, "exec", "-T", "caddy", *RELOAD),
                            timeout=60)  # fmt: skip
    if not reload.ok:
        raise failed("caddy_reload_failed")
    root = ctx.paths.etc / "ca" / "current" / "root.crt"
    started = ctx.deps.clock()
    while (ctx.deps.clock() - started).total_seconds() <= compose.HEALTH_SECONDS:
        try:
            code, _ = ctx.deps.https_get(host, "/api/health", root, 10.0)
        except (OSError, ssl.SSLError):
            code = 0
        if code == 200 and _served(ctx, host) == _file_leaf(ctx):
            ctx.log.line(step, "INFO", "Caddy reloaded; it serves the new certificate")
            return True
        ctx.deps.sleep(compose.POLL_SECONDS)
    raise failed("caddy_reload_failed")


def handle(ctx: Context, request: dict[str, Any]) -> dict[str, Any]:
    state = journal.load(ctx.paths)
    given = answers.load(ctx.paths)
    if state is None or given is None or not journal.done(state, 6):
        raise refused("not_installed")
    instance = str(state["project"])
    if backups.busy(ctx, ctx.step(0, "runner"), instance) or (
        backups.active_journal(ctx.paths, instance).exists()
    ):
        raise refused("runner_busy")
    for name in STAGED:
        (ctx.paths.etc / "tls" / name).unlink(missing_ok=True)
    host, image = given["public_host"], str(state["server_image"])
    result = install.run_ca(ctx, ctx.step(1, "renew"), image, "renew", host)
    install.run_ca(ctx, ctx.step(2, "check"), image, "check", host)
    install.give_key_to_caddy(ctx)
    trust.write(ctx, ctx.step(4, "trust"))
    reloaded = journal.done(state, 10) and _reload(
        ctx, ctx.step(5, "reload"), str(state["project"]), host
    )
    return {"code": result, "reloaded": bool(reloaded)}
