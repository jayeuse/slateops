"""Contracts for the Windows installer sources and their CI jobs (TASK-0091 W7, TASK-0094 W8).

The Windows-side scripts run only on Windows; their behavior tests are PowerShell tests in
``infra/windows/installer/tests`` that the ``windows-installer`` workflow runs on
``windows-latest``. These checks read the files: the workflow's action and shell rules, the
pinned Inno Setup download, the Inno Setup frame of the wizard spec (6.1, 12 item 2), and the
security rules that a text check can hold (ASCII files for Windows PowerShell 5.1, no
BitLocker key protector read, an Exec task action that takes no parameters).
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "infra/windows/installer"
WORKFLOW = ROOT / ".github/workflows/windows-installer.yml"
ISS = INSTALLER / "SlateOpsSetup.iss"
WIZARD = INSTALLER / "wizard/Wizard.iss"
COPY = INSTALLER / "wizard/Copy.iss"
RELEASE = ROOT / ".github/workflows/release.yml"
# The newest stable WSL at the W8 build (gh api repos/microsoft/WSL/releases, 2026-11-17:
# 3.0.5, asset wsl.3.0.5.0.x64.msi, digest sha256:2313efc5...).
WSL_URL = "https://github.com/microsoft/WSL/releases/download/3.0.5/wsl.3.0.5.0.x64.msi"
WSL_SHA256 = "2313efc5873e3f8552f42e77f950fabd913c0289078fa89d2100f3421a525eaa"
# Wizard spec section 3: words that never show on a default screen.
NEVER = (
    "WSL",
    "Linux",
    "Docker",
    "engine",
    "distribution",
    "VHD",
    "SMTP",
    "TLS",
    "STARTTLS",
    "mDNS",
    "Hyper-V",
    "PowerShell",
    "registry",
    "exit code",
    "root certificate",
    "CA",
)
# The spec's exceptions: Details texts, the "Other" email form, "Authenticated SMTP" in the
# Microsoft 365 steps and error, and a program the person installed (Docker Desktop, C25).
NEVER_ALLOWED = {
    "s05_details",
    "s09_ssl",
    "s09_starttls",
    "s09_m365_steps",
    "s09_err_m365",
    "c25_name",
    "c25_installed",
}
INNO_URL = "https://github.com/jrsoftware/issrc/releases/download/is-6_7_4/innosetup-6.7.4.exe"
# GitHub release asset digest of innosetup-6.7.4.exe (gh api repos/jrsoftware/issrc/releases,
# 2026-11-17).
INNO_SHA256 = "a549929319f9120716677c685535ca4671e4b937b5fdc87e2585f32d8eb30e8c"


def run_blocks(source: str) -> list[str]:
    return re.findall(r"(?ms)^\s+run: \|\n(.*?)(?=^\s+- |\Z)", source)


class WindowsInstallerWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = WORKFLOW.read_text(encoding="utf-8")

    def test_runs_for_the_installer_and_engine_contract_paths_p3_8(self) -> None:
        # P3-8: a change to the engine wire contract that the Windows side follows reruns the job.
        on = self.source.split("\non:\n", 1)[1].split("\nconcurrency:", 1)[0]
        self.assertIn("  pull_request:\n", on)
        self.assertIn("  push:\n    branches: [main]\n", on)
        for path in (
            '"infra/windows/installer/**"',
            '".github/workflows/windows-installer.yml"',
            '"packaging/engine/receive.py"',
            '"packaging/engine/status.py"',
            '"packaging/engine/log_bundle.py"',
            '"packaging/engine/release.py"',
        ):
            with self.subTest(path=path):
                self.assertEqual(on.count(path), 2)

    def test_reads_only_and_uses_only_allowed_sha_pinned_actions(self) -> None:
        self.assertIn("\npermissions:\n  contents: read\n", self.source)
        uses = re.findall(r"(?m)^\s+(?:- )?uses: (\S+)(.*)$", self.source)
        self.assertTrue(uses)
        for action, comment in uses:
            with self.subTest(action=action):
                name, _, revision = action.partition("@")
                self.assertTrue(name.startswith("actions/"))
                self.assertRegex(revision, r"^[0-9a-f]{40}$")
                self.assertRegex(comment, r"^ # v\d+\.\d+\.\d+$")
        self.assertIn("persist-credentials: false", self.source)

    def test_runs_on_windows_with_windows_powershell_and_no_expression_in_shell(self) -> None:
        self.assertIn("runs-on: windows-latest", self.source)
        steps = re.findall(r"(?ms)^      - name: .*?(?=^      - |\Z)", self.source)
        run_steps = [step for step in steps if "run: |" in step]
        self.assertEqual(len(run_steps), 2)
        for step in run_steps:
            with self.subTest(step=step.splitlines()[0]):
                self.assertIn("shell: powershell\n", step)
                self.assertNotIn("${{", step.split("run: |", 1)[1])

    def test_installs_the_pinned_inno_setup_after_a_sha256_check_and_compiles(self) -> None:
        self.assertIn(f"INNO_URL: {INNO_URL}", self.source)
        self.assertIn(f"INNO_SHA256: {INNO_SHA256}", self.source)
        compile_step = next(block for block in run_blocks(self.source) if "ISCC.exe" in block)
        check = compile_step.index("Get-FileHash")
        install = compile_step.index("Start-Process")
        self.assertLess(check, install)
        self.assertIn("SlateOpsSetup.iss", compile_step)
        self.assertIn("if ($LASTEXITCODE -ne 0)", compile_step)

    def test_runs_the_script_tests_in_a_separate_windows_powershell_process(self) -> None:
        test_step = next(block for block in run_blocks(self.source) if "run-tests.ps1" in block)
        self.assertIn(
            "powershell.exe -NoProfile -ExecutionPolicy Bypass -File "
            "infra\\windows\\installer\\tests\\run-tests.ps1",
            test_step,
        )
        self.assertIn("exit $LASTEXITCODE", test_step)


class WindowsInstallerSourcesTest(unittest.TestCase):
    def test_every_script_and_the_inno_project_are_ascii(self) -> None:
        # Copy.iss is UTF-8 (the spec's copy has "…", "·" and "→"; Inno Setup 6.3 and later
        # read UTF-8 scripts without a byte order mark).
        files = sorted(INSTALLER.rglob("*.ps1")) + [ISS, WIZARD]
        self.assertGreater(len(files), 10)
        for path in files:
            with self.subTest(path=path.relative_to(ROOT)):
                path.read_bytes().decode("ascii")

    def test_the_inno_project_has_the_wizard_frame_of_the_spec(self) -> None:
        setup = ISS.read_text(encoding="ascii").split("[Setup]\n", 1)[1].split("\n[", 1)[0]
        for line in (
            "WizardStyle=modern",
            "WizardSizePercent=150,150",
            "MinVersion=10.0",
            "ArchitecturesAllowed=x64compatible",
            "ArchitecturesInstallIn64BitMode=x64compatible",
            "PrivilegesRequired=admin",
            "DisableWelcomePage=no",
        ):
            with self.subTest(line=line):
                self.assertIn(f"\n{line}\n", f"\n{setup}\n")

    def test_no_inno_line_starts_with_a_hash_that_is_not_a_directive(self) -> None:
        # The Inno preprocessor reads a line that starts with "#" as a directive, so a Pascal
        # line that starts with a character constant such as #13#10 stops the compile.
        directive = re.compile(
            r"\s*#(include|define|if|ifdef|ifndef|else|elif|endif|expr|emit|error|pragma|undef)\b"
        )
        for path in (ISS, WIZARD, COPY):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith("#"):
                    self.assertRegex(line, directive, f"{path.name}:{number}")

    def test_no_wizard_procedure_is_used_before_its_declaration(self) -> None:
        # Inno's Pascal Script resolves names in file order: a procedure used above its
        # declaration (with no forward declaration) stops the compile.
        lines = WIZARD.read_text(encoding="utf-8").splitlines()
        head = re.compile(r"\s*(procedure|function)\s+(\w+)", re.IGNORECASE)
        declared: dict[str, int] = {}
        for number, line in enumerate(lines, 1):
            match = head.match(line)  # a forward declaration counts as a declaration
            if match:
                declared.setdefault(match.group(2).lower(), number)
        for number, line in enumerate(lines, 1):
            code = re.sub(r"\{[^}]*\}", "", re.sub(r"'[^']*'", "''", line)).split("//")[0]
            for name in re.findall(r"\b\w+\b", code):
                first = declared.get(name.lower())
                self.assertFalse(
                    first is not None and first > number,
                    f"Wizard.iss:{number} uses {name} (declared at {first})",
                )

    def test_bitlocker_is_never_read_beyond_its_status_p2_4(self) -> None:
        # P2-4, S91-10: the BitLocker module loads every key protector, so no script calls it.
        for path in sorted((INSTALLER / "scripts").rglob("*.ps1")):
            code = [
                line
                for line in path.read_text(encoding="ascii").splitlines()
                if not line.lstrip().startswith("#")
            ]
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertNotRegex(
                    "\n".join(code), r"(?i)KeyProtector|RecoveryPassword|Get-BitLockerVolume"
                )

    def test_the_task_actions_take_no_parameters(self) -> None:
        for name in ("exec.ps1", "start.ps1"):
            with self.subTest(name=name):
                source = (INSTALLER / "scripts" / name).read_text(encoding="ascii")
                self.assertIn("[CmdletBinding()]\nparam()\n", source)


class WizardCopyTest(unittest.TestCase):
    """WZ-4 and the WZ-11 static proxy (spec 11): the copy and the controls of the pages."""

    def copy(self) -> dict[str, str]:
        text = COPY.read_text(encoding="utf-8").split("[CustomMessages]\n", 1)[1]
        pairs = (
            line.split("=", 1)
            for line in text.splitlines()
            if "=" in line and not line.startswith(";")
        )
        return {key: value for key, value in pairs}

    def test_wz4_no_default_screen_shows_a_word_of_the_never_list(self) -> None:
        copy = self.copy()
        self.assertGreater(len(copy), 200)
        for key, value in copy.items():
            if key in NEVER_ALLOWED or key.endswith("_details"):
                continue
            with self.subTest(key=key):
                for word in NEVER:
                    self.assertNotRegex(value, rf"(?<![A-Za-z]){re.escape(word)}(?![A-Za-z])")
                self.assertNotRegex(value, r"\b(80|443|465|587|5353)\b")

    def test_wz11_text_is_never_a_tlabel_and_every_key_the_code_uses_exists(self) -> None:
        code = WIZARD.read_text(encoding="ascii")
        self.assertNotRegex(code, r"\bTLabel\b")
        used = set(re.findall(r"\b(?:CM|FM)\('([a-z0-9_]+)'", code))
        prefixed = {"s12_stage", "s12_fail", "stage_"}
        missing = {key for key in used - set(self.copy()) if key not in prefixed}
        self.assertEqual(missing, set())

    def test_w8_2_the_password_field_is_never_saved_or_logged(self) -> None:
        # Plan 3.2 check 4: no page value goes to SetPreviousData, and no Log line names the
        # password or the key.
        code = WIZARD.read_text(encoding="ascii")
        self.assertNotIn("SetPreviousData(", code)
        for line in re.findall(r"(?m)^.*\bLog\(.*$", code):
            with self.subTest(line=line.strip()):
                self.assertNotRegex(line, r"MailPassword|KeyText|PipeFrame|PipeOutput|JobText")


class InstallerReleaseJobTest(unittest.TestCase):
    """W8-7 and the ISCC carry (TASK-0091): the release builds one setup file below 2 GiB."""

    def setUp(self) -> None:
        source = RELEASE.read_text(encoding="utf-8")
        self.job = source.split("\n  installer:\n", 1)[1].split("\n  release:\n", 1)[0]
        self.release = source.split("\n  release:\n", 1)[1]

    def test_w8_7_one_setup_file_from_this_runs_artifacts_below_2_gib(self) -> None:
        self.assertIn("runs-on: windows-latest", self.job)
        self.assertRegex(
            self.job,
            r"(?m)^    needs: \[check, images, engine-bundle, linux-image, manifest, notices\]$",
        )
        for name in (
            "asset-images",
            "asset-engine",
            "asset-linux",
            "asset-manifest",
            "asset-notices",
        ):
            with self.subTest(name=name):
                self.assertIn(f"name: {name}\n", self.job)
        self.assertIn('"/DPayloadDir=$payload"', self.job)
        self.assertIn("SlateOpsSetup.iss", self.job)
        self.assertIn("-ge 2147483648", self.job)
        self.assertIn("name: asset-installer\n", self.job)
        # The release job takes every asset-* artifact and refuses one of 2 GiB or more.
        self.assertIn("pattern: asset-*", self.release)
        self.assertRegex(self.release, r"(?m)^    needs: \[.*\binstaller\]$")

    def test_the_wsl_package_and_inno_setup_are_pinned_and_checked_before_use(self) -> None:
        self.assertIn(f"WSL_URL: {WSL_URL}", self.job)
        self.assertIn(f"WSL_SHA256: {WSL_SHA256}", self.job)
        self.assertIn("WSL_VERSION: 3.0.5.0", self.job)
        self.assertIn(f"INNO_URL: {INNO_URL}", self.job)
        self.assertIn(f"INNO_SHA256: {INNO_SHA256}", self.job)
        self.assertLess(self.job.index("$env:WSL_SHA256"), self.job.index("WriteAllText"))
        self.assertLess(self.job.index("$env:INNO_SHA256"), self.job.index("Start-Process"))
        # version.json holds what Read-SetupVersion (Exec.ps1) requires.
        for key in (
            "schema_version",
            "version",
            "wsl_version",
            "wsl_msi_sha256",
            "linux_image_sha256",
        ):
            with self.subTest(key=key):
                self.assertIn(f'"{key}":', self.job)


if __name__ == "__main__":
    unittest.main()
