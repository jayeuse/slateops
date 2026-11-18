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
# W9: included after Wizard.iss, in this order (SlateOpsSetup.iss).
MAINTENANCE = INSTALLER / "wizard/Maintenance.iss"
UNINSTALL = INSTALLER / "wizard/Uninstall.iss"
CODE_FILES = (WIZARD, MAINTENANCE, UNINSTALL)


def pascal_code() -> str:
    """The [Code] text in include order, as the compiler reads it."""
    return "\n".join(path.read_text(encoding="ascii") for path in CODE_FILES)


def code_only(text: str) -> str:
    """Pascal text with { } comments, // comments and string contents removed; newlines stay,
    so line numbers hold. A brace inside a string is not a comment."""
    out: list[str] = []
    state = "code"
    index = 0
    while index < len(text):
        char = text[index]
        if state == "code":
            if char == "'":
                state = "string"
                out.append("''")
            elif char == "{":
                state = "brace"
            elif text.startswith("//", index):
                state = "line"
            else:
                out.append(char)
        elif state == "string":
            if char == "'":
                state = "code"
            elif char == "\n":
                out.append(char)
        elif state == "brace":
            if char == "}":
                state = "code"
            elif char == "\n":
                out.append(char)
        elif char == "\n":
            state = "code"
            out.append(char)
        index += 1
    return "".join(out)


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
        # Compile, the [Code] self-test (W14-D1, TASK-0097), the script tests.
        self.assertEqual(len(run_steps), 3)
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
        files = sorted(INSTALLER.rglob("*.ps1")) + [ISS, *CODE_FILES]
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
        for path in (ISS, *CODE_FILES, COPY):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith("#"):
                    self.assertRegex(line, directive, f"{path.name}:{number}")

    def test_no_semicolon_comment_line_inside_code(self) -> None:
        # W9: Maintenance.iss and Uninstall.iss lie inside [Code], where ";" is not a comment.
        after_code = pascal_code().split("\n[Code]\n", 1)[1]
        for number, line in enumerate(after_code.splitlines(), 1):
            self.assertFalse(line.lstrip().startswith(";"), f"[Code] line {number}: {line}")

    def test_no_wizard_procedure_is_used_before_its_declaration(self) -> None:
        # Inno's Pascal Script resolves names in file order: a procedure used above its
        # declaration (with no forward declaration) stops the compile.
        lines = pascal_code().splitlines()
        head = re.compile(r"\s*(procedure|function)\s+(\w+)", re.IGNORECASE)
        declared: dict[str, int] = {}
        for number, line in enumerate(lines, 1):
            match = head.match(line)  # a forward declaration counts as a declaration
            if match:
                declared.setdefault(match.group(2).lower(), number)
        for number, code in enumerate(code_only(pascal_code()).splitlines(), 1):
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
        code = pascal_code()
        self.assertNotRegex(code, r"\bTLabel\b")
        used = set(re.findall(r"\b(?:CM|FM[1-3])\('([a-z0-9_]+)'", code))
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


def routine(code: str, head: str) -> str:
    """The text of one Pascal routine, from its heading to the next routine."""
    start = code.index(head)
    following = re.search(r"(?m)^(procedure|function) ", code[start + len(head) :])
    return code[start : start + len(head) + (following.start() if following else len(code))]


class WizardJobRunnerTest(unittest.TestCase):
    """W8 correction 1 (TASK-0094): the secret channel and Save report in the job runner."""

    def setUp(self) -> None:
        self.code = WIZARD.read_text(encoding="ascii")

    def test_b1_the_job_reads_its_pipe_output_by_a_flag_that_the_pipe_poller_never_clears(
        self,
    ) -> None:
        # Code review B-1: PollPipe clears PipeExpectOutput when the service closes its end, so
        # a job that keyed its result on it lost the install result and the recovery key.
        poll_job = routine(self.code, "procedure PollJob;")
        self.assertRegex(
            poll_job,
            r"if JobPipeOut then\s+begin\s+\{[^}]*\}\s+PollPipe;\s+JobText := PipeResult;",
        )
        self.assertNotIn("JobPipeOut :=", routine(self.code, "procedure PollPipe;"))

    def test_f1_no_blocking_job_names_a_pipe_input_job(self) -> None:
        # Security F-1: RunJobBlocking writes an input file, which Exec refuses for a pipe-input
        # job (input_on_disk); the smtp-test discard must go through the pipe.
        exec_source = (INSTALLER / "scripts/lib/Exec.ps1").read_text(encoding="ascii")
        listed = re.search(r"PipeInputJobs\s*=\s*@\(([^)]*)\)", exec_source)
        self.assertIsNotNone(listed)
        pipe_input = set(re.findall(r"'([a-z-]+)'", listed.group(1)))
        self.assertIn("smtp-test", pipe_input)
        blocking = re.findall(r"RunJobBlocking\('([a-z-]+)'", self.code)
        self.assertTrue(blocking)
        self.assertEqual(sorted(set(blocking) & pipe_input), [])

    def test_b3_save_report_works_while_a_job_runs(self) -> None:
        # QA B1, code B-3: in the S12 slow state a job runs; Save report must still save.
        save = routine(self.code, "procedure SaveReport(Sender: TObject);\nvar")
        self.assertNotRegex(save, r"if JobRunning then\s+Exit;")
        self.assertIn("not JobRunning then\n    RunJobBlocking('log-bundle'", save)


class UninstallAndMaintenanceTest(unittest.TestCase):
    """W9 (TASK-0096): what a static read can show of the uninstaller and the settings program."""

    def test_f4c_the_uninstaller_uses_no_setup_only_call(self) -> None:
        # Inno Setup help: at uninstall there is no WizardForm, no ExtractTemporaryFiles and no
        # *AsOriginalUser call; the wizard's helpers that use them or {tmp} stay out too.
        # Code only: ";" comment lines and { } comments are left out.
        text = UNINSTALL.read_text(encoding="ascii")
        code = re.sub(
            r"\{[^}]*\}",
            "",
            "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(";")),
        )
        forbidden = (
            "WizardForm",
            "{tmp}",
            "ExtractTemporaryFile",
            "AsOriginalUser",
            "NewOut",
            "RunHelper",
            "StartHelper",
            "AddTextTo",
            "InfoForm",
            "FailureForm",
            "SaveReport(",
            "OpenAsUser",
        )
        for name in forbidden:
            with self.subTest(name=name):
                self.assertNotIn(name, code)
        self.assertIn("function InitializeUninstall(): Boolean;", code)
        # Plan F4c: U01 removes nothing; the work runs at usUninstall, where an exception stops
        # the uninstall before Inno removes a file.
        initialize = routine(code, "function InitializeUninstall(): Boolean;")
        self.assertNotRegex(initialize, r"uninstall-(stop|data)|remove-windows")
        self.assertIn("usUninstall", code)

    def test_w9_5_modify_opens_the_settings_program_which_cannot_install(self) -> None:
        iss = ISS.read_text(encoding="ascii")
        settings = iss.split("#ifdef SettingsBuild", 1)[1].split("#else", 1)[0]
        for line in ("Uninstallable=no", "CreateUninstallRegKey=no", "CreateAppDir=no"):
            with self.subTest(line=line):
                self.assertIn(f"\n{line}\n", settings)
        self.assertIn(
            'DestDir: "{commonappdata}\\SlateOps\\settings"; DestName: "SlateOpsSettings.exe"', iss
        )
        post = routine(pascal_code(), "procedure CurStepChanged(CurStep: TSetupStep);")
        self.assertIn("'ModifyPath'", post)
        self.assertIn("'NoModify', 0", post)
        self.assertIn("HKLM64", post)
        self.assertIn("SETTINGS_BUILD", routine(pascal_code(), "function PrepareToInstall("))
        for workflow in (WORKFLOW, RELEASE):
            with self.subTest(workflow=workflow.name):
                text = workflow.read_text(encoding="utf-8")
                self.assertLess(
                    text.index("/DSettingsBuild"), text.index('"/DSettingsExe=$settings"')
                )


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


def read_copy() -> dict[str, str]:
    text = COPY.read_text(encoding="utf-8").split("[CustomMessages]\n", 1)[1]
    pairs = (
        line.split("=", 1) for line in text.splitlines() if "=" in line and not line.startswith(";")
    )
    return {key: value for key, value in pairs}


class UpdatePathTest(unittest.TestCase):
    """W13b part 2 (TASK-0095): the setup program's update path M05, as a static read shows it.
    The PowerShell side (the WSL step, the result read) is in tests/Update.Tests.ps1."""

    def setUp(self) -> None:
        self.code = code_only(pascal_code())

    def test_p2_1_a_newer_setup_opens_m05_and_the_settings_program_stays_on_m01(self) -> None:
        start = routine(self.code, "function InitializeSetup(): Boolean;")
        self.assertRegex(
            start, r"if \(EntryScreen = ''\) and SETTINGS_BUILD then\s+EntryScreen := ''"
        )
        self.assertNotRegex(start, r"if EntryScreen = ''\s+then\s+EntryScreen := ''")
        # The literal values are blanked by code_only; the raw text names them.
        raw = routine(pascal_code(), "function InitializeSetup(): Boolean;")
        self.assertIn(
            "if (EntryScreen = 'M05') and SETTINGS_BUILD then\n    EntryScreen := 'M01';", raw
        )
        self.assertIn("RunId := NewRunId('update');", raw)
        skip = routine(pascal_code(), "function ShouldSkipPage(PageID: Integer): Boolean;")
        self.assertIn("Result := (PageID <> Pages[P_UPDATE].ID) and (PageID <> wpFinished);", skip)

    def test_p2_2_the_windows_part_changes_only_after_the_engine_reports_success(self) -> None:
        raw = pascal_code()
        post = routine(raw, "procedure CurStepChanged(CurStep: TSetupStep);")
        self.assertRegex(
            post,
            r"if EntryScreen <> 'M05' then\s+begin\s+OutFile := NewOut\('save'\);\s+"
            r"RunHelper\('save-progress', RunId, OutFile, '-Stage install_finished'\);",
        )
        poll = routine(raw, "procedure PollUpdate;\nvar")
        # The scripts copy and Next (Inno's file copy) follow only "updated" or
        # "version_not_newer" (an update that the tick finished, section 12).
        self.assertRegex(
            poll,
            r"if \(JobExit = 0\) or \(JobCode = 'version_not_newer'\) then\s+begin\s+"
            r"UpdEngineDone := True;\s+UpdStep\('scripts', 'update-done', ''\);",
        )
        # The second call is Try again after a failed scripts copy, once the engine is done.
        self.assertEqual(raw.count("'update-done'"), 2)
        self.assertRegex(
            routine(raw, "function UpdateNext: Boolean;\nbegin"),
            r"if UpdFailed and UpdEngineDone then\s+begin\s+UpdFailed := False;\s+"
            r"UpdStep\('scripts', 'update-done', ''\);",
        )
        self.assertEqual(raw.count("UpdEngineDone := True;"), 1)
        self.assertIn(
            "Result := UpdPhase = 'done';", routine(raw, "function UpdateNext: Boolean;\nbegin")
        )

    def test_p2_3_the_result_sentence_follows_the_update_state(self) -> None:
        result = routine(pascal_code(), "procedure UpdateFailed;")
        self.assertRegex(
            result, r"if UpdState = 'rolled_back' then\s+UpdFail\(4, FM1\('m05_rolled_back'"
        )
        self.assertRegex(
            result,
            r"else if UpdState = 'needs_support' then\s+UpdFail\(4, CM\('m05_support'\), False\)",
        )
        self.assertRegex(
            result,
            r"JobCode = 'insufficient_space' then\s+UpdFail\(2, FM1\('m05_space', UpdNeedsGb\)",
        )
        self.assertEqual(pascal_code().count("'m05_rolled_back'"), 1)

    def test_p2_4_cancel_in_m05_never_removes_anything(self) -> None:
        cancel = routine(
            pascal_code(),
            "procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);",
        )
        branch = cancel.split("if EntryScreen = 'M05' then", 1)
        self.assertEqual(len(branch), 2, "M05 has its own branch")
        self.assertLess(
            cancel.index("if EntryScreen = 'M05' then"), cancel.index("AskCancelChoice")
        )
        m05 = branch[1].split("Exit;", 1)[0]
        self.assertNotIn("RemoveEverything", m05)
        self.assertIn("UpdCanStop", m05)
        # No dead end: Close works in the slow state of the engine job, which goes on alone.
        stop = routine(pascal_code(), "function UpdCanStop: Boolean;\nbegin")
        self.assertIn("((UpdPhase = 'update') and UpdSlowShown)", stop)
        skip = routine(pascal_code(), "function ShouldSkipPage(PageID: Integer): Boolean;")
        self.assertLess(skip.index("EntryScreen = 'M05'"), skip.index("P_KEY"))

    def test_p2_5_the_wizard_gives_no_time_limit_verdict_on_a_running_update(self) -> None:
        raw = pascal_code()
        # Only the engine update job has purpose 'update'; receive keeps the runner's limit.
        self.assertEqual(re.findall(r"StartJob\('([a-z-]+)'[^;]*, 'update', ", raw), ["update"])
        self.assertIn("StartJob('receive', ", raw)
        self.assertRegex(raw, r"StartJob\('receive', [^;]*'updreceive', False, False, 15\)")
        # At the slow point the task's last result is read once, as on S12.
        self.assertIn(
            "if TaskTimeoutCode = 'service_logon_failed' then",
            routine(raw, "procedure PollUpdate;\nvar"),
        )
        poll = routine(pascal_code(), "procedure PollJob;")
        self.assertIn(
            "(JobPurpose <> 'install') and (JobPurpose <> 'update') and "
            "(Elapsed(JobStartedAt) > JobLimitMs)",
            poll,
        )

    def test_w13b_5_the_wsl_step_has_its_own_limit_and_shows_f10(self) -> None:
        raw = pascal_code()
        limit = re.search(r"WSL_LIMIT_MS = ([0-9]+);", raw)
        self.assertIsNotNone(limit)
        # 10 minutes after msiexec, plus the idle check and three 60 s waits on code 1618.
        self.assertGreater(int(limit.group(1)), 600000 + 4 * 60000)
        poll = routine(raw, "procedure PollUpdate;\nvar")
        self.assertRegex(poll, r"Code = 'wsl_not_back' then\s+UpdFail\(1, CM\('f10'\), True\)")
        self.assertRegex(poll, r"Code = 'engine_busy' then\s+UpdPause\('wsl'\)")
        helper = (INSTALLER / "scripts/setup-helper.ps1").read_text(encoding="ascii")
        for action in ("'update-prepare'", "'update-wsl'", "'update-done'"):
            with self.subTest(action=action):
                self.assertIn(action, helper.split("[string]$Action", 1)[0])

    def test_m05_copy_is_the_spec_text(self) -> None:
        copy = read_copy()
        expected = {
            "m05_title": "Update Slate Operations",
            "m05_subtitle": "Version %1 is installed. This setup installs version %2.",
            "m05_backup": "Setup makes a backup before it changes anything. If the update "
            "fails, Slate Operations goes back to version %1 by itself.",
            "m05_next": "Update &now",
            "m05_done": "Slate Operations is updated to version %1.",
            "m05_rolled_back": "The update did not work. Slate Operations went back to version "
            "%1. Everybody must sign in again.",
            "f10": "The server part did not start again after a Windows update of one of its "
            "parts.",
        }
        for key, value in expected.items():
            with self.subTest(key=key):
                self.assertEqual(copy.get(key), value)


class W9ReviewCorrectionTest(unittest.TestCase):
    """Round-2 review of W9 and M05 (TASK-0096, TASK-0095): what a static read of the setup
    program shows. The PowerShell side is in the Windows tests (Wizard, Checks, Uninstall and
    Update .Tests.ps1)."""

    def setUp(self) -> None:
        self.raw = pascal_code()

    def test_item_1_a_resumed_kept_reinstall_stays_kept_and_never_deletes_kept_data(self) -> None:
        start = routine(self.raw, "function InitializeSetup(): Boolean;")
        self.assertRegex(
            start, r"if Pos\('\"kept\":true', StateText\) > 0 then\s+begin\s+KeptState := 'kept';"
        )
        self.assertIn("KeptFor := DataRoot;", start)
        # No second restore: with the disk already back, the resume starts at import-kept.
        self.assertRegex(
            start,
            r"if FileExists\(AddBackslash\(DataRoot\) \+ 'kept\\ext4\.vhdx'\) then\s+"
            r"BgIndex := 1\s+else\s+BgIndex := 3;",
        )
        later = routine(self.raw, "function LaterSaveExtra(Discarded: Boolean): String;")
        self.assertEqual(later.count("if KeptMode then\n    Extra := Extra + ' -KeptMark';"), 1)
        install = routine(self.raw, "procedure InstallNextStep;")
        self.assertIn("if KeptMode then\n      Extra := Extra + ' -KeptMark';", install)
        # W14-D9: "Remove everything" runs from the timer (PollCloseFlow).
        remove = routine(self.raw, "procedure PollCloseFlow;\nvar")
        self.assertRegex(
            remove,
            r"if \(DataRoot <> ''\) and FileExists\(AddBackslash\(DataRoot\) \+ "
            r"'kept\\kept\.json'\) then\s+CloseStep\('data', [^;]*'kept-return', ''\)",
        )
        self.assertNotIn("KeptMode", remove)
        helper = (INSTALLER / "scripts/setup-helper.ps1").read_text(encoding="ascii")
        self.assertIn("if ($KeptMark) { $marks.kept = $true }", helper)

    def test_item_1_no_helper_parameter_name_is_reused_as_a_variable(self) -> None:
        # PowerShell names ignore case, and a typed parameter keeps its type: a switch -Kept
        # turns the helper's own "$kept = Get-KeptPaths ..." into an error.
        helper = (INSTALLER / "scripts/setup-helper.ps1").read_text(encoding="ascii")
        block = helper.split("[CmdletBinding()]", 1)[1].split("\n)\n", 1)
        names = re.findall(r"\]\$([A-Za-z]+)", block[0])
        self.assertIn("RunId", names)
        for name in names:
            with self.subTest(name=name):
                self.assertNotRegex(block[1], rf"(?im)^\s*\${name}\s*=")

    def test_item_1_a_kept_resume_after_the_background_finished_is_done(self) -> None:
        start = routine(self.raw, "function InitializeSetup(): Boolean;")
        self.assertNotIn("BgIndex := 7;", start)
        self.assertLess(start.index("KeptFor := DataRoot;"), start.index("BgIndex := BgCount;"))

    def test_item_1_import_kept_repeats_safely_on_a_resume(self) -> None:
        exec_source = (INSTALLER / "scripts/lib/Exec.ps1").read_text(encoding="ascii")
        kept = exec_source.split("'import-kept' {", 1)[1].split("'wsl-facts' {", 1)[0]
        self.assertLess(kept.index("'--list', '--quiet'"), kept.index("'--import-in-place'"))
        self.assertIn("$Result.code = 'already_imported'", kept)

    def test_n1_a_resumed_kept_reinstall_shows_the_organization_name(self) -> None:
        # Design N-1: S07 does not run on a resume, so the name comes from kept.json through the
        # helper at start; the row is left out while the name is still empty.
        start = routine(self.raw, "function InitializeSetup(): Boolean;")
        kept = start.split("KeptFor := DataRoot;", 1)[1].split("end;", 1)[0]
        self.assertIn("NewOutRun('kept-read', '-DataRoot ' + AddQuotes(DataRoot)", kept)
        self.assertIn("KeptName := JsonValue(Text, 'business_name');", kept)
        ready = routine(self.raw, "procedure RenderReady;")
        self.assertRegex(
            ready, r"if KeptName <> '' then\s+AddRow\(FM1\('s11_org', KeptName\), -1\);"
        )
        helper = (INSTALLER / "scripts/setup-helper.ps1").read_text(encoding="ascii")
        self.assertIn("-Restored:$Restored", helper)

    def test_option_b_m01_names_repair_for_a_missing_backup_drive(self) -> None:
        sentence = routine(self.raw, "function MaintSentence(var Line: String): String;")
        self.assertIn("FM1('m01_needs_backup_repair', Copy(MaintBackupFolder, 1, 2))", sentence)
        copy = read_copy()
        self.assertIn("select Repair", copy.get("m01_needs_backup_repair", ""))
        self.assertEqual(
            copy.get("c29_uninstall_leftovers"),
            "This PC has parts left by an earlier Slate Operations uninstall. Setup removes them "
            "before it continues. Your data and backups do not change.",
        )

    def test_item_2_a_kept_failure_on_s11_can_open(self) -> None:
        ready = routine(self.raw, "procedure RenderReady;")
        self.assertIn(
            "WizardForm.NextButton.Enabled := (not KeptMode) or BgDone or BgFailed;", ready
        )
        poll = routine(self.raw, "procedure PollBackground;")
        self.assertEqual(poll.count("RedrawKeptReady;"), 2)

    def test_item_3_c29_uninstall_leftovers_run_remove_windows(self) -> None:
        click = routine(self.raw, "procedure ItemButtonClick(Sender: TObject);")
        self.assertRegex(
            click,
            r"\(Id = 'C29'\) and \(Items\[Index\]\.Code = 'uninstall_leftovers'\) then\s+"
            r"StartFix\('remove-windows', ''\)",
        )
        checks = (INSTALLER / "scripts/lib/Checks.ps1").read_text(encoding="ascii")
        self.assertIn("uninstall_log     =", checks)
        self.assertIn("c29_uninstall_leftovers=", COPY.read_text(encoding="utf-8"))

    def test_item_4_uninstall_failures_offer_save_report(self) -> None:
        text = UNINSTALL.read_text(encoding="ascii")
        self.assertNotIn("MsgBox(CM('u04_keep_failed'), mbError, MB_OK);", text)
        step = routine(text, "procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);")
        self.assertIn("UStopped(CM('u04_keep_failed'), True);", step)
        self.assertIn("UStopped(CM('f4c_stopped'), True);", step)
        self.assertRegex(
            step,
            r"if ULeft = 'data' then\s+Extra := '-DataLeft';\s+"
            r"Text := URun\('remove-windows', URunId, Extra\);",
        )

    def test_item_5_m01_names_a_changed_network(self) -> None:
        sentence = routine(self.raw, "function MaintSentence(var Line: String): String;")
        self.assertRegex(
            sentence,
            r"else if MaintNetwork then\s+begin\s+Result := CM\('m01_needs_network'\);\s+"
            r"Line := CM\('m01_runs_line'\);",
        )
        self.assertIn("MaintNetwork := JsonLiteral(Text, 'network_changed') = 'true';", self.raw)

    def test_item_6_the_s09_resume_keeps_the_started_install(self) -> None:
        later = routine(self.raw, "function LaterSaveExtra(Discarded: Boolean): String;")
        self.assertIn(
            "if (InstallStep >= 2) or (EntryNext = 'S12') or (EntryNext = 'S09') then", later
        )

    def test_item_7_m02_has_no_continue_later(self) -> None:
        build = routine(self.raw, "procedure BuildMailPage;")
        self.assertIn("Later.Visible := EntryScreen <> 'M01';", build)

    def test_item_8_the_start_menu_report_says_what_it_does_first(self) -> None:
        entry = routine(self.raw, "function SettingsEntry: Boolean;\nbegin")
        self.assertLess(entry.index("CM('report_start')"), entry.index("SaveReport(nil);"))

    def test_item_9_a_drive_change_without_a_key_says_so(self) -> None:
        poll = routine(self.raw, "procedure PollMaint;\nvar")
        self.assertIn("BackToMaint(FM1('m03_key_failed', MaintTarget))", poll)

    def test_item_12_m04_asks_before_the_key_changes(self) -> None:
        click = routine(self.raw, "procedure MaintActionClick(Sender: TObject);")
        self.assertRegex(
            click, r"5: begin\s+if not ConfirmNewKey then\s+Exit;\s+StartMaintKey\('key4'\);"
        )
        confirm = routine(self.raw, "function ConfirmNewKey: Boolean;")
        self.assertIn("Back.Default := True;", confirm)
        self.assertIn("CM('m04_confirm_text')", confirm)

    def test_item_13_s06_before_s14_has_no_cancel_answer(self) -> None:
        cancel = routine(
            self.raw,
            "procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);",
        )
        self.assertLess(cancel.index("if EntryNext = 'S14' then"), cancel.index("AskCancelChoice"))
        # Only S06 and S14 close; every other page of that session (Inno's file copy) refuses.
        self.assertIn(
            "Cancel := (CurPageID = Pages[P_BACK].ID) or (CurPageID = Pages[P_KEY].ID);", cancel
        )
        changed = routine(self.raw, "procedure CurPageChanged(CurPageID: Integer);")
        self.assertIn("WizardForm.CancelButton.Visible := EntryNext <> 'S14';", changed)

    def test_item_14_the_copy_is_the_design_text(self) -> None:
        copy = read_copy()
        expected = {
            "u02_text": "This deletes all your records, files and settings in Slate Operations on "
            "this PC. It cannot be undone.",
            "s07_kept_older": "This data is from Slate Operations version %1. This setup cannot "
            "open it. Install with setup version %1 first, then run this setup to update.",
            "m01_runs_line": "Slate Operations is running.",
            "m01_not_installed": "Slate Operations is not installed on this PC. To install it, "
            "open the Slate Operations setup file.",
            "report_start": "Setup saves a report for Slate Operations support. This takes up "
            "to 3 minutes.",
            "m03_key_failed": "Backups now go to %1, but setup could not make their recovery "
            "key. Select Make a new recovery key now.",
            "m04_confirm_title": "Make a new recovery key?",
            "m04_confirm_text": "Your current recovery key stops working. Have a printer or a "
            "USB drive ready to save the new key.",
            "m04_confirm_go": "&Make a new key",
            "m04_first": "Your old recovery key no longer works. Save this new key now.",
            "m01_needs_network": "Needs attention: the network changed. Select Repair.",
            "m05_stage1": "Prepare the update",
            "m05_people": "People cannot use Slate Operations while it updates. This can take "
            "up to 1 hour. Tell your people before you start.",
            "m05_space": "The server part of Slate Operations needs %1 GB of free space for a "
            "safe update. Nothing changed. Select Save report and send the file to Slate "
            "Operations support.",
            "m05_support": "The update did not finish, and Slate Operations could not go back "
            "by itself. Select Save report and send the file to Slate Operations support.",
            "m05_finish_failed": "Slate Operations is updated to version %1, but setup could "
            "not finish its part on this PC.",
            "m05_slow_close": "The update goes on by itself. You can close setup now. Later, run "
            "this setup again and select Update now. Setup then finishes the update on this PC.",
        }
        for key, value in expected.items():
            with self.subTest(key=key):
                self.assertEqual(copy.get(key), value)


class W14DefectTest(unittest.TestCase):
    """W14 defects (TASK-0097) that a static read of the setup program can hold."""

    def setUp(self) -> None:
        self.raw = pascal_code()
        self.code = code_only(self.raw)

    def test_w14_d1_no_script_routine_hands_on_an_open_array(self) -> None:
        # W14-D1: S02 stopped at its first FM call ("Runtime error (at 72:16): Type Mismatch."):
        # FM took "Args: array of String" and passed it on to FmtMessage. FmtMessage now gets
        # only a bracket literal, from wrappers with a fixed number of values.
        heads = re.findall(r"(?m)^(?:procedure|function)\s+\w+\(([^)]*)\)", self.code)
        self.assertTrue(heads)
        for params in heads:
            with self.subTest(params=params):
                self.assertNotIn("array of", params)
        calls = re.findall(r"FmtMessage\(([^;]*)", self.raw)
        self.assertTrue(calls)
        for call in calls:
            with self.subTest(call=call):
                self.assertRegex(call, r"^CM\(Key\), \[")
        self.assertNotRegex(self.code, r"\bFM\(")

    def test_w14_d1_a_draw_failure_on_s02_shows_the_failure_with_save_report(self) -> None:
        check = routine(self.raw, "procedure RenderCheck;")
        self.assertRegex(check, r"try\s+RenderCheckBody;\s+except")
        self.assertIn("Log('S02 draw failed: ' + GetExceptionMessage);", check)
        self.assertIn("CheckDrawFailed := True;", check)
        self.assertIn("CM('s02_draw_failed')", check)
        self.assertIn("CM('btn_save_report')", check)
        nxt = routine(self.raw, "function NextButtonClick(CurPageID: Integer): Boolean;")
        self.assertRegex(
            nxt,
            r"if CheckDrawFailed then\s+begin\s+CheckDrawFailed := False;\s+"
            r"StartCheck\('check', 'S02'\);",
        )

    def test_w14_d1_ci_runs_the_code_self_test_with_a_red_control(self) -> None:
        # Parent decision: a /DSelfTest build runs the [Code] on the Windows runner (hidden) and
        # fails the job on any fault; a /DSelfTestRed build must report the W14-D1 pattern.
        workflow = WORKFLOW.read_text(encoding="utf-8")
        step = workflow.split("name: Run the setup program's [Code] self-test (W14-D1)", 1)
        self.assertEqual(len(step), 2, "the self-test step exists")
        body = step[1].split("\n      - name:", 1)[0]
        for text in ("/DSelfTest", "/DSelfTestRed", "/SELFTESTOUT=", "/VERYSILENT", "'DONE'"):
            with self.subTest(text=text):
                self.assertIn(text, body)
        self.assertIn("FAIL open-array", body)
        self.assertLess(workflow.index("self-test (W14-D1)"), workflow.index("run-tests.ps1"))
        selftest = (INSTALLER / "wizard/SelfTest.iss").read_text(encoding="ascii")
        for call in (
            "FM1(",
            "FM2(",
            "FM3(",
            "RenderCheckBody;",
            "P_EMAIL",
            "P_READY",
            "P_INSTALL",
            "P_KEY",
            "RenderFinishedPage",
            "P_MAINT",
            "P_UPDATE",
            "'check-owner.json'",
            "'check-ready.json'",
        ):
            with self.subTest(call=call):
                self.assertIn(call, selftest)
        owner = (INSTALLER / "tests/fixtures/check-owner.json").read_text(encoding="ascii")
        self.assertIn(
            '{"id":"C04","class":"fix","code":"off","values":{"uefi":true,'
            '"bitlocker_caution":false,"maker":"Gigabyte Technology Co., Ltd."}}',
            owner,
        )
        self.assertEqual(owner.count('{"id":"C'), 30)
        iss = ISS.read_text(encoding="ascii")
        self.assertIn('#ifdef SelfTest\n#include "wizard\\SelfTest.iss"\n#endif', iss)

    def test_w14_d7_s07_preselects_the_c07_drive(self) -> None:
        # W14-D7: S07 listed "E: · Most space" first but had C: selected. The default comes from
        # the C07 drive (else the first, largest drive) whatever DataRoot held; the checked radio
        # takes the focus, so no other radio is checked by focus; a click that changes nothing
        # draws nothing.
        load = routine(self.raw, "procedure LoadDataDrives(Text: String);")
        self.assertRegex(load, r"Best := C07Drive;\s+DataRoot := '';")
        self.assertIn(
            "LoadDataDrives(ReadText(OutFile));", routine(self.raw, "procedure ReadDataDrives;")
        )
        render = routine(self.raw, "procedure RenderData;")
        self.assertRegex(
            render,
            r"if DriveRadios\[I\]\.Checked and DriveRadios\[I\]\.CanFocus then\s+"
            r"WizardForm\.ActiveControl := DriveRadios\[I\];",
        )
        click = routine(self.raw, "procedure DriveRadioClick(Sender: TObject);")
        self.assertIn("if DataRendering then", click)
        self.assertIn(
            "if CompareText(Copy(DataRoot, 1, 2), "
            "DriveLetters[TNewRadioButton(Sender).Tag]) = 0 then",
            click,
        )
        selftest = (INSTALLER / "wizard/SelfTest.iss").read_text(encoding="ascii")
        self.assertIn("SelfDrives(", selftest)

    def test_w14_d9_continue_later_and_remove_everything_never_hold_the_window(self) -> None:
        # W14-D9: "Continue later" froze the window (a Sleep loop waited for the stuck job). Both
        # flows now run from the timer with time limits; no routine of theirs sleeps or waits.
        self.assertNotIn("procedure SaveContinueLater;", self.raw)
        self.assertNotIn("procedure RemoveEverything;", self.raw)
        self.assertNotIn("KeepAndClose", self.raw)
        for head in (
            "procedure StartCloseFlow(Flow, After: String);\nbegin",
            "procedure PollCloseFlow;\nvar",
            "procedure CloseStep(Phase, Line, Action, Extra: String);\nbegin",
        ):
            with self.subTest(head=head):
                body = routine(self.raw, head)
                for blocking in ("Sleep(", "RunPipeJobBlocking(", "RunJobBlocking(", "NewOutRun("):
                    self.assertNotIn(blocking, body)
        self.assertIn(
            "PollCloseFlow;", routine(self.raw, "procedure TimerTick(H, Msg, Id, Tick: Longword);")
        )
        for limit in ("CLOSE_WAIT_MS", "CLOSE_STEP_MS"):
            self.assertIn(limit, routine(self.raw, "procedure PollCloseFlow;\nvar"))
        cancel = routine(
            self.raw,
            "procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);",
        )
        self.assertIn("StartCloseFlow('later', 'close');", cancel)
        self.assertIn("StartCloseFlow('remove', 'close');", cancel)

    def test_w14_d8_the_job_poll_asks_the_helper_and_has_limits(self) -> None:
        # W14-D8: the poll never collected a finished Windows-side result on the owner's PC. The
        # job-result helper is asked every 15 s too; its answer and its start have limits.
        poll = routine(self.raw, "procedure PollJob;\nvar")
        self.assertIn("if (not Found) and (Elapsed(JobPollAt) < JOB_ASK_MS) then", poll)
        self.assertIn("if not StartHelper('job-result', RunId, JobResultOut,", poll)
        self.assertIn("(Elapsed(JobResultAt) > JOB_ANSWER_MS)", poll)
        selftest = (INSTALLER / "wizard/SelfTest.iss").read_text(encoding="ascii")
        self.assertIn('"request_id":"b6b02c87-f769-41b1-8c56-4aabfdc2dd94"', selftest)
        self.assertIn("SelfPoll;", selftest)
        self.assertIn("SelfCloseFlow;", selftest)

    def test_w14_d1_s02_offers_save_report(self) -> None:
        items = routine(self.raw, "procedure AddCheckItems(OnlyFix: Boolean);")
        self.assertLess(items.index("CM('btn_check_again')"), items.index("AddReportControls;"))


if __name__ == "__main__":
    unittest.main()
