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
    # Spec S05 subtitle (rule 2.8): "Windows finishes Virtual Machine Platform and WSL when this
    # PC restarts." names the component by the short name that Windows shows beside the long one.
    "s05_subtitle",
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
        # Compile, the [Code] self-test (W14-D1, TASK-0097), the script tests, the real Exec job
        # path (W14-D8) and the DEC-0039 mDNS spike.
        self.assertEqual(len(run_steps), 5)
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
            # Spec section 3 exception (rule 2.8): the component name that Windows shows.
            value = value.replace("Windows Subsystem for Linux (WSL)", "")
            with self.subTest(key=key):
                for word in NEVER:
                    self.assertNotRegex(value, rf"(?<![A-Za-z]){re.escape(word)}(?![A-Za-z])")
                self.assertNotRegex(value, r"\b(80|443|465|587|5353)\b")

    def test_wz11_text_is_never_a_tlabel_and_every_key_the_code_uses_exists(self) -> None:
        code = pascal_code()
        self.assertNotRegex(code, r"\bTLabel\b")
        used = set(re.findall(r"\b(?:CM|FM[1-3])\('([a-z0-9_]+)'", code))
        prefixed = {"s12_stage", "s12_fail", "stage_", "bg_stage_", "s01_state_", "strip_name_"}
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
        # Security F-1: a job input file is refused by Exec for a pipe-input job (input_on_disk).
        # W14-D9: RunJobBlocking is gone, so every job starts through StartJob, and a pipe-input
        # job always passes PipeIn True. (DEC-0041: no discard is sent any more.)
        exec_source = (INSTALLER / "scripts/lib/Exec.ps1").read_text(encoding="ascii")
        listed = re.search(r"PipeInputJobs\s*=\s*@\(([^)]*)\)", exec_source)
        self.assertIsNotNone(listed)
        pipe_input = set(re.findall(r"'([a-z-]+)'", listed.group(1)))
        self.assertIn("smtp-test", pipe_input)
        self.assertNotIn("RunJobBlocking", self.code)
        calls = re.findall(r"StartJob\('([a-z-]+)', (.*?)\);", pascal_code(), re.S)
        self.assertTrue(calls)
        for name, rest in calls:
            if name in pipe_input:
                with self.subTest(job=name):
                    self.assertEqual(rest.rsplit(", ", 3)[1], "True")

    def test_b3_save_report_works_while_a_job_runs(self) -> None:
        # QA B1, code B-3: in the S12 slow state a job runs; Save report must still save.
        save = routine(self.code, "procedure SaveReport(Sender: TObject);\nbegin")
        self.assertNotRegex(save, r"if JobRunning then\s+Exit;")
        self.assertRegex(
            pascal_code(),
            r"if \(ServiceSid <> ''\) and not JobRunning and ReportJobAllowed then\s+begin\s+"
            r"ReportPhase := 'linux';\s+"
            r"StartJob\('log-bundle'",
        )


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
            cancel.index("if EntryScreen = 'M05' then"), cancel.index("RunRemoval('close');")
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
        # At the slow point the task's last result decides, as on S12. W14-D9: it is the
        # job-result answer that the poll already asked for, not a blocking helper call.
        self.assertIn("if JobLogonFailed then", routine(raw, "procedure PollUpdate;\nvar"))
        poll = routine(pascal_code(), "procedure PollJob;")
        self.assertIn("(JobPurpose <> 'update') and (Elapsed(JobStartedAt) > JobLimitMs)", poll)

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
        install = routine(self.raw, "procedure InstallNextStep;")
        self.assertIn("if KeptMode then\n      Extra := Extra + ' -KeptMark';", install)
        # DEC-0041: the removal never deletes kept data, whatever mode this run is in; the
        # helper decides from the data folder (Remove-SetupData, Removal.Tests.ps1).
        remove = routine(self.raw, "procedure PollCloseFlow;\nvar")
        self.assertIn("'setup-remove-data'", remove)
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

    def test_item_1_import_kept_repeats_safely_on_a_resume(self) -> None:
        exec_source = (INSTALLER / "scripts/lib/Exec.ps1").read_text(encoding="ascii")
        kept = exec_source.split("'import-kept' {", 1)[1].split("'wsl-facts' {", 1)[0]
        self.assertLess(kept.index("'--list', '--quiet'"), kept.index("'--import-in-place'"))
        self.assertIn("$Result.code = 'already_imported'", kept)

    def test_n1_a_resumed_kept_reinstall_shows_the_organization_name(self) -> None:
        # Design N-1: the row is left out while the name is still empty.
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
            r"Text := URun\('remove-windows', URunId, Extra, U_WINDOWS_SEC\);",
        )

    def test_item_5_m01_names_a_changed_network(self) -> None:
        sentence = routine(self.raw, "function MaintSentence(var Line: String): String;")
        self.assertRegex(
            sentence,
            r"else if MaintNetwork then\s+begin\s+Result := CM\('m01_needs_network'\);\s+"
            r"Line := CM\('m01_runs_line'\);",
        )
        self.assertIn("MaintNetwork := JsonLiteral(Text, 'network_changed') = 'true';", self.raw)

    def test_item_7_m02_has_no_continue_later(self) -> None:
        # DEC-0041: no "Continue later" anywhere (M02 never had one).
        self.assertNotIn("ContinueLater", self.raw)
        self.assertNotIn("s09_continue_later", read_copy())

    def test_item_8_the_start_menu_report_says_what_it_does_first(self) -> None:
        entry = routine(self.raw, "function SettingsEntry: Boolean;\nvar")
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
        self.assertLess(
            cancel.index("if EntryNext = 'S14' then"), cancel.index("RunRemoval('close');")
        )
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
        # DEC-0039: 27 checks (C15, C16 and C30 are gone).
        self.assertEqual(owner.count('{"id":"C'), 27)
        iss = ISS.read_text(encoding="ascii")
        self.assertIn('#ifdef SelfTest\n#include "wizard\\SelfTest.iss"\n#endif', iss)

    def test_w14_d7_s07_keeps_the_persons_drive(self) -> None:
        # W14-D7 closed as not a defect (the owner chose D: himself); the part-1 change that reset
        # the drive on every load is reverted (parent decision). The default (the first, largest
        # drive) is set only while no folder is chosen, so a chosen drive stays after Back and
        # Next; no focus or click guard is left.
        load = routine(self.raw, "procedure LoadDataDrives(Text: String);")
        self.assertIn("if (DataRoot = '') and (Count > 0) then", load)
        self.assertNotIn("DataRoot := '';", load)
        self.assertNotIn("C07Drive", self.raw)
        self.assertNotIn("DataRendering", self.raw)
        render = routine(self.raw, "procedure RenderData;")
        self.assertNotIn("WizardForm.ActiveControl := DriveRadios[I];", render)
        selftest = (INSTALLER / "wizard/SelfTest.iss").read_text(encoding="ascii")
        drives = routine(selftest, "procedure SelfDrives;")
        self.assertIn("DataRoot := '';", drives)
        self.assertIn("DriveRadioClick(DriveRadios[1]);", drives)
        self.assertIn("(DataRoot = 'E:\\SlateOps')", drives)
        self.assertIn("(DataRoot = 'D:\\SlateOps')", drives)

    def test_w14_d9_continue_later_and_remove_everything_never_hold_the_window(self) -> None:
        # W14-D9: "Continue later" froze the window (a Sleep loop waited for the stuck job). The
        # removal runs from the timer with time limits; no routine of it sleeps or waits.
        self.assertNotIn("procedure SaveContinueLater;", self.raw)
        self.assertNotIn("procedure RemoveEverything;", self.raw)
        self.assertNotIn("KeepAndClose", self.raw)
        for head in (
            "procedure StartCloseFlow(Flow, After: String);\nbegin",
            "procedure PollCloseFlow;\nvar",
            "procedure CloseStep(Number: Integer; Phase, Line, Action, Extra: String; "
            "LimitMs: Cardinal);\nbegin",
        ):
            with self.subTest(head=head):
                body = routine(self.raw, head)
                for blocking in ("Sleep(", "RunPipeJobBlocking(", "RunJobBlocking(", "NewOutRun("):
                    self.assertNotIn(blocking, body)
        self.assertIn(
            "PollCloseFlow;", routine(self.raw, "procedure TimerTick(H, Msg, Id, Tick: Longword);")
        )
        for limit in (
            "REMOVE_STEP_MS",
            "REMOVE_DATA_MS",
            "REMOVE_FEATURES_MS",
            "REMOVE_WINDOWS_MS",
        ):
            self.assertIn(limit, routine(self.raw, "procedure PollCloseFlow;\nvar"))
        cancel = routine(
            self.raw,
            "procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);",
        )
        self.assertIn("RunRemoval('close');", cancel)
        self.assertIn("StartCloseFlow('remove', RemoveWhy);", self.raw)

    def test_w14_d8_the_job_poll_asks_the_helper_and_has_limits(self) -> None:
        # W14-D8: the poll never collected a finished Windows-side result on the owner's PC. The
        # job-result helper is asked every 15 s too; its answer and its start have limits.
        poll = routine(self.raw, "procedure PollJob;\nvar")
        self.assertIn(
            "if ((not Found) or JobAnswered) and (Elapsed(JobPollAt) < JOB_ASK_MS) then", poll
        )
        # W14-D9: Save report's log-bundle job keeps its own run ID (JobRunId).
        self.assertIn("if not StartHelper('job-result', JobRunId, JobResultOut,", poll)
        self.assertIn("(Elapsed(JobResultAt) > JOB_ANSWER_MS)", poll)
        selftest = (INSTALLER / "wizard/SelfTest.iss").read_text(encoding="ascii")
        self.assertIn('"request_id":"b6b02c87-f769-41b1-8c56-4aabfdc2dd94"', selftest)
        self.assertIn("SelfPoll;", selftest)
        self.assertIn("SelfCloseFlow;", selftest)

    def test_w14_d1_s02_offers_save_report(self) -> None:
        # W14-D3 (6.1 L5): Check again and Save report share one row.
        items = routine(self.raw, "procedure AddCheckItems(OnlyFix: Boolean);")
        self.assertLess(items.index("CM('btn_check_again')"), items.index("AddReportButton;"))


def routines(code: str) -> dict[str, str]:
    """Each routine of a Pascal text by its heading line (code only), to the next heading."""
    heads = list(re.finditer(r"(?m)^(?:procedure|function) [^\n]*", code))
    return {
        head.group(0): code[
            head.start() : heads[index + 1].start() if index + 1 < len(heads) else len(code)
        ]
        for index, head in enumerate(heads)
    }


ENGINE_PROGRESS = ROOT / "packaging/engine/progress.py"
# Spec 7.6 helper keys (parent decision: final), as the copy names them: step_<group>_<key>.
HELPER_STEP_KEYS = (
    "pc_unpack", "pc_vmp", "pc_wsl", "pc_busy", "pc_check", "data_unpack", "data_folder",
    "bg_service", "bg_wslconfig", "bg_import", "bg_restore_kept", "bg_import_kept", "bg_start",
    "bg_kept_status", "backup_check", "win_firewall", "win_hosts", "win_trust", "win_power",
    "win_lid", "win_https", "repair_r7", "repair_account", "repair_tasks", "repair_firewall",
    "repair_hosts", "repair_backup", "repair_start", "upd_idle", "upd_unpack", "upd_copy",
    "upd_wsl", "upd_scripts",
)  # fmt: skip
# Engine jobs with no wizard line: the nightly renewal, and prepare-uninstall, which runs inside
# the uninstall-stop helper (U03 shows its stage text).
ENGINE_JOBS_WITHOUT_LINE = ("renew-certificate", "prepare-uninstall")


class W14Part2Test(unittest.TestCase):
    """W14 fix round part 2 (TASK-0097): no wait holds the window (W14-D9) and every wait shows
    its stages, action and time (W14-D5, spec 2.4, 6.1 progress block, 7.6)."""

    def setUp(self) -> None:
        self.raw = pascal_code()
        self.code = code_only(self.raw)
        self.wizard = code_only(
            WIZARD.read_text(encoding="ascii") + MAINTENANCE.read_text(encoding="ascii")
        )

    def test_w14_d9_only_listed_routines_wait_in_the_window(self) -> None:
        # A blocking call in the wizard disables the window until it returns (Inno 6.7
        # Setup.ScriptFunc: Exec runs under a TWindowDisabler). Allowed: the plumbing itself,
        # the start before any window, Inno's own install step, the one-file-per-tick unpacking
        # and the small notices file.
        allowed = {
            "function RunHelper(": {"ewWaitUntilTerminated"},
            "function NewOutRun(": {"RunHelper("},
            "function InitializeSetup(": {"RunHelper(", "NewOutRun(", "ExtractTemporaryFiles("},
            "procedure CurStepChanged(": {"RunHelper(", "NewOutRun("},
            "procedure NoticesClick(": {"ExtractTemporaryFiles("},
            "procedure ExtractNextPart;": {"ExtractTemporaryFiles("},
        }
        blocking = (
            "RunHelper(",
            "NewOutRun(",
            "RunJobBlocking(",
            "Sleep(",
            "ExtractTemporaryFiles(",
            "ExtractTemporaryFile(",
            "TaskTimeoutCode",
            "ewWaitUntilTerminated",
        )
        found = {}
        for head, body in routines(self.wizard).items():
            calls = {call for call in blocking if call in body.split("\n", 1)[1]}
            if calls:
                found[head] = calls
        self.assertTrue(found)
        for head, calls in found.items():
            with self.subTest(routine=head):
                rule = next((key for key in allowed if head.startswith(key)), None)
                self.assertIsNotNone(rule, f"{head} waits: {sorted(calls)}")
                self.assertLessEqual(calls, allowed[rule])

    def test_w14_d9_the_waits_run_from_the_timer(self) -> None:
        tick = routine(self.raw, "procedure TimerTick(H, Msg, Id, Tick: Longword);")
        for poll in ("PollStep;", "PollReport;", "PollExtract;", "RefreshWaitLabels;"):
            with self.subTest(poll=poll):
                self.assertIn(poll, tick)
        # Save report inside a modal form (S13 form) and in the settings program before the
        # wizard exists still moves: the tick runs the report before its ModalOpen exit.
        self.assertLess(tick.index("PollReport;"), tick.index("if Ticking or ModalOpen then"))
        step = routine(self.raw, "procedure PollStep;")
        self.assertIn("StepLimitMs", step)
        self.assertIn("StepFinished(", step)
        # Each step past its limit ends with a visible message, never a silent wait.
        self.assertIn("'helper_timeout'", step)
        # The settings program starts the timer for its Start menu report.
        entry = routine(self.raw, "function SettingsEntry: Boolean;\nvar")
        self.assertIn("StartTimer;", entry)
        self.assertLess(entry.index("CM('report_start')"), entry.index("SaveReport(nil);"))

    def test_w14_d9_u03_shows_each_stage_and_ticks_while_inno_waits(self) -> None:
        # Inno's Exec pumps messages while it waits (Setup.InstFunc HandleProcessWait) but
        # disables the windows; U03 has no button, so a timer callback keeps its line and time.
        text = UNINSTALL.read_text(encoding="ascii")
        step = routine(text, "procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);")
        self.assertIn("SetTimer(0, 0, 1000, CreateCallback(@UTick));", text)
        for call in ("uninstall-stop", "uninstall-data", "remove-windows"):
            with self.subTest(call=call):
                before = step[: step.index(f"URun('{call}'")]
                self.assertRegex(before[-400:], r"UStage\([123], ")
        report = routine(text, "procedure USaveReport;")
        self.assertIn("UReportForm", report)

    def test_w14_d5_engine_lines_are_read_from_the_job_standard_error(self) -> None:
        exec_source = (INSTALLER / "scripts/lib/Exec.ps1").read_text(encoding="ascii")
        self.assertIn(
            "[System.IO.File]::Open($StderrPath, [System.IO.FileMode]::CreateNew, "
            "[System.IO.FileAccess]::Write, [System.IO.FileShare]::Read)",
            exec_source,
        )
        copy_loop = exec_source.split("public static class CappedCopy", 1)[1].split(
            "return total;", 1
        )[0]
        self.assertRegex(copy_loop, r"target\.Write\([^;]*\);\s*target\.Flush\(\);")
        err = routine(self.raw, "function JobErrFile: String;")
        self.assertIn("'.stderr.txt'", err)
        read = routine(self.raw, "procedure ReadProgressFile(")
        self.assertIn("LoadStringFromLockedFile(", read)
        self.assertIn("ReadJobProgress;", routine(self.raw, "procedure PollJob;\nvar"))
        parse = routine(self.raw, "function ParseProgressLine(")
        for word in ("'progress'", "'start'", "'done'"):
            with self.subTest(word=word):
                self.assertIn(word, parse)

    def test_w14_d5_every_engine_step_and_helper_key_has_its_line(self) -> None:
        steps = {}
        text = ENGINE_PROGRESS.read_text(encoding="utf-8")
        block = text.split("STEPS: dict[str, tuple[str, ...]] = {", 1)[1].split("}", 1)[0]
        for job, keys in re.findall(r'"([a-z-]+)": \(([^)]*)\)', block):
            steps[job] = re.findall(r'"([a-z_]+)"', keys)
        self.assertIn("install", steps)
        copy = read_copy()
        names = [f"step_{group}" for group in HELPER_STEP_KEYS]
        for job, keys in steps.items():
            if job in ENGINE_JOBS_WITHOUT_LINE:
                continue
            names += [f"step_{job.replace('-', '_')}_{key}" for key in keys]
        for name in names:
            with self.subTest(name=name):
                self.assertTrue(copy.get(name), name)

    def test_w14_d5_the_helper_writes_its_steps_beside_its_result(self) -> None:
        helper = (INSTALLER / "scripts/setup-helper.ps1").read_text(encoding="ascii")
        self.assertIn("Set-HelperProgressFile -Path ($script:outPath + '.progress')", helper)
        common = (INSTALLER / "scripts/lib/Common.ps1").read_text(encoding="ascii")
        self.assertIn("function Write-HelperProgress {", common)
        self.assertIn("'progress {0} {1}/{2} {3} start'", common)
        sources = "\n".join(
            path.read_text(encoding="ascii") for path in (INSTALLER / "scripts").rglob("*.ps1")
        )
        for group, keys in (
            ("pc", ("vmp", "wsl", "busy", "check")),
            ("win", ("firewall", "hosts", "trust", "power")),
            ("repair", ("r7", "account", "tasks", "firewall", "hosts", "backup", "start")),
        ):
            for key in keys:
                with self.subTest(step=f"{group}.{key}"):
                    self.assertRegex(
                        sources,
                        rf"Write-HelperProgress -Job '{group}' -Number \S+ -Total \d+ -Key '{key}'",
                    )
        checks = (INSTALLER / "scripts/lib/Checks.ps1").read_text(encoding="ascii")
        reader = checks.split("function Invoke-Reader {", 1)[1].split("\n}", 1)[0]
        self.assertIn("Write-CheckProgress -Reader $Name", reader)
        # The wizard reads the file that the helper writes.
        self.assertIn(
            "+ '.progress'", routine(self.raw, "function ProgressFileOf(OutFile: String): String;")
        )

    def test_w14_d5_no_bar_or_spinner_and_one_time_label(self) -> None:
        self.assertNotIn("npbstMarquee", self.code)
        self.assertNotIn("AddMarquee", self.code)
        block = routine(self.raw, "procedure AddProgress(")
        for name in (
            "WaitTime",
            "WaitNow",
            "CM('s12_done_word')",
            "CM('s12_now_word')",
            "CM('wait_next_word')",
        ):
            with self.subTest(name=name):
                self.assertIn(name, block)
        body = routine(self.raw, "procedure BeginBody(Index: Integer);")
        for name in (
            "WaitTime := nil;",
            "WaitNow := nil;",
            "StepLabel := nil;",
            "ReportLabel := nil;",
        ):
            with self.subTest(name=name):
                self.assertIn(name, body)
        refresh = routine(self.raw, "procedure RefreshWaitLabels;")
        # Spec 6.3 (7334a07c): a tick sets the time text and the bar position only (BarRefresh).
        self.assertIn("BarRefresh;", refresh)
        self.assertIn("if WaitTime <> nil then", routine(self.raw, "procedure BarRefresh;"))
        self.assertNotIn("RenderPage(", refresh)
        copy = read_copy()
        self.assertEqual(copy.get("wait_line"), "%1 of %2: %3 · %4")
        # Spec 6.3 (7334a07c): the time text of a wait is "<time> so far" (wait_so_far).
        self.assertEqual(copy.get("wait_so_far"), "%1 so far")
        self.assertEqual(copy.get("wait_now"), "Now: %1")

    def test_w14_d5_d9_the_self_test_covers_the_new_waits(self) -> None:
        selftest = (INSTALLER / "wizard/SelfTest.iss").read_text(encoding="ascii")
        for name in (
            "SelfProgressLines;",
            "SelfEngineStep;",
            "SelfCheckStep;",
            "SelfWaitRedraw;",
            "SelfStepRunner;",
            "SelfReport;",
        ):
            with self.subTest(name=name):
                self.assertIn(name, routine(selftest, "procedure RunSelfTest;"))
        self.assertIn("'Now: Setting up the database.'", selftest)


def brace_comments(text: str) -> list[tuple[int, str]]:
    """Each { } comment of a Pascal text (outside strings and // comments) with its line. A
    comment ends at the first }, as the Inno Setup compiler reads it."""
    found: list[tuple[int, str]] = []
    index = 0
    state = "code"
    while index < len(text):
        char = text[index]
        if state == "code":
            if char == "'":
                state = "string"
            elif text.startswith("//", index):
                state = "line"
            elif char == "{":
                end = text.find("}", index + 1)
                end = len(text) if end < 0 else end
                found.append((text.count("\n", 0, index) + 1, text[index + 1 : end]))
                index = end
        elif state == "string":
            if char == "'" or char == "\n":
                state = "code"
        elif char == "\n":
            state = "code"
        index += 1
    return found


class InnoCommentTest(unittest.TestCase):
    """CI run 44239562945 on ad20c28c: "{ Patterns: file patterns under {tmp}\\payload ... }" ended
    the comment at the } of {tmp}, and the rest was read as code (Syntax error, compile aborted)."""

    def test_no_brace_inside_a_brace_comment(self) -> None:
        files = (*CODE_FILES, INSTALLER / "wizard/SelfTest.iss")
        for path in files:
            text = path.read_text(encoding="ascii")
            if path == WIZARD:
                text = text.split("\n[Code]\n", 1)[1]
            comments = brace_comments(text)
            self.assertTrue(comments, path.name)
            for line, comment in comments:
                with self.subTest(file=path.name, line=line):
                    self.assertNotIn("{", comment)


# Spec (rule 2.8, sections 4.5, 5.2, S05, S12, U04, 7.5): the copy that names what setup did.
SPEC_NAMED_COPY = {
    "s02_ready_prep_both": "Setup will turn on Virtual Machine Platform and install Windows "
    "Subsystem for Linux (WSL), then restart this PC once.",
    "s05_subtitle": "Windows finishes Virtual Machine Platform and WSL when this PC restarts.",
    "s05_done": "Setup turned on Virtual Machine Platform and installed Windows Subsystem for "
    "Linux (WSL). Windows finishes them when this PC restarts.",
    "s05_why_vmp": "Virtual Machine Platform: lets this PC run the server part of Slate "
    "Operations.",
    "s05_why_wsl": "Windows Subsystem for Linux (WSL): runs the server part of Slate Operations "
    "inside Windows.",
    "s05_failed": "Setup could not turn on Virtual Machine Platform.",
    "s05_failed_wsl": "Setup could not install Windows Subsystem for Linux (WSL).",
    "s12_stage1": "Load the Slate Operations programs",
    "s12_stage2": "Create the settings and passwords",
    "u04_feature": "Virtual Machine Platform and Windows Subsystem for Linux (WSL) stay on this "
    "PC, because other programs can use them.",
}


class W14Part3Test(unittest.TestCase):
    """W14 fix round part 3 (TASK-0097): the layout rules of spec 6.1 (W14-D3) and rule 2.8, name
    things (W14-D6), as a static read can hold them. The self-test checks the drawn pages."""

    def setUp(self) -> None:
        self.raw = pascal_code()

    def test_w14_d3_l1_the_grey_is_fixed_at_its_source(self) -> None:
        # The body panel painted clBtnFace and every text on it took that color; S08 and S09,
        # built on the page surface, never showed grey (screenshots 4 to 11).
        body = routine(self.raw, "procedure BeginBody(Index: Integer);")
        self.assertIn("Bodies[Index].ParentBackground := False;", body)
        self.assertIn("Bodies[Index].Color := Pages[Index].SurfaceColor;", body)
        verdict = routine(self.raw, "function AddVerdict(S: String): TNewMemo;")
        self.assertIn("Result.Color := Cur.Color;", verdict)
        self.assertNotIn("WizardForm.Color", code_only(self.raw))
        self.assertIn("external 'HideCaret@user32.dll stdcall';", self.raw)
        self.assertIn("HideCaret(Verdict.Handle);", routine(self.raw, "procedure FocusVerdict("))
        # S08 sits on the page surface: its strip is built there (spec 6.2, 7334a07c); M02 is a
        # maintenance form and has no strip.
        self.assertIn("OrgTop := StageLineAt(Surface, 0, StripStep(P_ORG));", self.raw)
        self.assertIn("MailTop := 0;", self.raw)
        self.assertIn("Y := OrgTop;", routine(self.raw, "procedure LayoutOrg;\nvar"))
        self.assertIn("Y := MailTop;", routine(self.raw, "procedure LayoutMail;\nvar"))

    def test_w14_d3_l2_to_l5_rhythm_and_rows(self) -> None:
        self.assertIn(
            "CurY := CurY + Result.Height + ScaleY(4);",
            routine(self.raw, "function AddText(S: String; Bold: Boolean): TNewStaticText;"),
        )
        self.assertIn("ScaleY(8)", routine(self.raw, "procedure ItemGap;"))
        self.assertIn("ScaleY(12)", routine(self.raw, "procedure BlockGap;"))
        self.assertIn(
            "RowX := RowX + Result.Width + ScaleX(8);", routine(self.raw, "function AddRowButton(")
        )
        items = routine(self.raw, "procedure AddCheckItems(OnlyFix: Boolean);")
        self.assertNotIn("s02_recommended", items)
        self.assertIn("AddLinkLine(FM1('s02_passed'", items)
        self.assertNotIn("AddButtonAt(", items)
        for head in (
            "procedure AddItemButtons(Index: Integer);",
            "procedure RenderInstall;",
            "procedure RenderKey;",
        ):
            with self.subTest(head=head):
                self.assertNotIn("AddButtonAt(", routine(self.raw, head))
        failure = routine(self.raw, "procedure AddFailure(")
        self.assertIn("AddReportButton;", failure)

    def test_w14_d3_l6_l11_the_button_row(self) -> None:
        # Every caption change of Inno's row goes through a setter that sizes and aligns it.
        direct = re.findall(
            r"(?m)^.*\b(?:NextButton|CancelButton|BackButton|ExtraButton)\.Caption :=.*$",
            code_only(self.raw),
        )
        self.assertEqual(len(direct), 3, direct)
        layout = routine(self.raw, "procedure LayoutButtonRow;")
        self.assertIn("PlaceRowButton(WizardForm.NextButton, Right);", layout)
        self.assertIn(
            "WizardForm.CalculateButtonWidth([Caption])",
            routine(self.raw, "function RowButtonWidth("),
        )
        self.assertIn(
            "LayoutButtonRow;", routine(self.raw, "procedure CurPageChanged(CurPageID: Integer);")
        )
        # 6.1 L6: S01 Save report and S15 "Open Slate Operations" are page buttons.
        self.assertNotIn("ExtraButton.OnClick := @SaveReport;", self.raw)
        self.assertNotIn("ExtraButton.OnClick := @OpenAppClick;", self.raw)
        self.assertIn("S15Open.Parent := WizardForm.FinishedPage;", self.raw)
        self.assertIn("S01Report.Parent := WizardForm.WelcomePage;", self.raw)

    def test_w14_d3_l7_l9_l10_lines_forms_and_drives(self) -> None:
        self.assertIn(
            "AddLinkLine(FM1('s07_folder', DataRoot), CM('s07_change_folder'), 0);", self.raw
        )
        self.assertIn("AddLinkLine(ReportLine, CM('btn_show_in_folder'), 0);", self.raw)
        build = routine(self.raw, "procedure BuildMailPage;")
        self.assertNotIn("SurfaceHeight", build)
        self.assertIn("MailError := AddTextTo(Surface, 0, '', False);", build)
        self.assertIn("OrgError := AddTextTo(Surface, 0, '', False);", self.raw)
        self.assertIn(
            "OrgConfirm.SetBounds(Half + ScaleX(16), Y, Half, OrgConfirm.Height);",
            routine(self.raw, "procedure LayoutOrg;\nvar"),
        )
        self.assertIn("ScaleX(16)", routine(self.raw, "procedure PlaceRadioRow("))
        copy = read_copy()
        self.assertEqual(copy.get("drive_row"), "%1 (%2) · %3 GB free")
        self.assertEqual(copy.get("drive_row_most"), "%1 (%2) · %3 GB free · Most space")
        self.assertEqual(copy.get("drive_usb_name"), "%1 (USB drive)")
        self.assertEqual(copy.get("drive_local_disk"), "Local Disk")
        self.assertIn("external 'GetVolumeInformationW@kernel32.dll stdcall';", self.raw)

    def test_w14_d3_s09_other_uses_two_rows_and_must_fit(self) -> None:
        # Parent decision (2026-11-18, option 1): with Other, Server and Port share a row and User
        # name and Password share a row; the only exception to the full-width rule (spec 6.1 rule
        # 9). The self-test FAILs when that state does not end above the status line.
        layout = routine(self.raw, "procedure LayoutMail;\nvar")
        self.assertIn(
            "MailPort.SetBounds(Full - PortWidth, Y, PortWidth, MailPort.Height);", layout
        )
        self.assertIn(
            "MailPassword.SetBounds(Half + ScaleX(16), Y, Half, MailPassword.Height);", layout
        )
        # The wizard is 165% high (parent decision); Inno 6.7.4 caps WizardSizePercent at 150,
        # so the [Code] adds the rest before any page is built.
        start = routine(self.raw, "procedure InitializeWizard;")
        self.assertLess(
            start.index("WizardForm.ClientHeight := (WizardForm.ClientHeight * 165) div 150;"),
            start.index("CreateCustomPage("),
        )
        self.assertIn("WizardSizePercent=150,150\n", ISS.read_text(encoding="ascii"))
        # "Show" on the Password label's line (parent decision, 2026-11-18).
        self.assertIn(
            "MailShow.SetBounds(Full - ShowWidth, Y, ShowWidth, MailShow.Height);", layout
        )
        spec = (ROOT / "docs/specs/windows-installer-wizard.md").read_text(encoding="utf-8")
        rule = spec.split("  9. **Forms (S08, S09, M02, M03).**", 1)[1].split("\n", 1)[0]
        # R-3 (Product Designer): the pin names the two row exceptions, not one exact sentence,
        # so the rule can say that S08 and S09 Other both have one.
        self.assertIn("S09 with Other selected shows Server and Port in one row", rule)
        self.assertIn('Password and "Type the password again" share one row', rule)
        self.assertIn('"Show" sits at the right end of the Password label\'s line', rule)
        selftest = (INSTALLER / "wizard/SelfTest.iss").read_text(encoding="ascii")
        forms = routine(selftest, "procedure SelfFormPages;")
        self.assertIn("SelfRecord('W14-D3 M02 Other with every field fits the page', Ok,", forms)
        self.assertIn("MailStatus.Top + MailStatus.Height <= StatusBandTop - ScaleY(12)", forms)
        self.assertNotIn("SelfInfo('W14-D3 S09 Other, every field'", forms)

    def test_w14_d6_the_copy_names_what_setup_did(self) -> None:
        copy = read_copy()
        for key, value in SPEC_NAMED_COPY.items():
            with self.subTest(key=key):
                self.assertEqual(copy.get(key), value)
        for key, value in copy.items():
            with self.subTest(key=key):
                self.assertNotRegex(value, r"(?i)\b(the|a) Windows feature\b|\ba feature that\b")

    def test_w14_d3_the_self_test_checks_every_changed_page(self) -> None:
        selftest = (INSTALLER / "wizard/SelfTest.iss").read_text(encoding="ascii")
        run = routine(selftest, "procedure RunSelfTest;")
        for call in (
            "SelfButtonRow;",
            "SelfForms;",
            "SelfFormPages;",
            "SelfPageStates;",
            "SelfFits('S02 owner', P_CHECK);",
        ):
            with self.subTest(call=call):
                self.assertIn(call, run)
        fits = routine(selftest, "procedure SelfFits(Name: String; Index: Integer);")
        for check in (
            "SelfButtonsFit(Bad)",
            "Pages[Index].SurfaceColor",
            "CurY > Limit",
            "Limit := StatusBandTop - ScaleY(12);",
        ):
            with self.subTest(check=check):
                self.assertIn(check, fits)
        self.assertIn("BuildFailureForm(", selftest)
        self.assertIn("BuildKeyForm(", selftest)


if __name__ == "__main__":
    unittest.main()


SCRIPTS = INSTALLER / "scripts"
PS_TESTS = INSTALLER / "tests"
SELFTEST = INSTALLER / "wizard/SelfTest.iss"
# Product Designer, W14 re-check round (TASK-0097, run 2026-11-18-w14-fix-round-design-review):
# the exact strings that AC-6 and AC-7 name.
RECHECK_COPY = {
    "later_save_failed": "Setup could not save your progress, so it stays open. To try again, "
    "select the same action again.",
    "later_restart_failed": "Setup saved your progress but could not restart this PC. Restart it "
    "from the Start menu.",
    "report_failed": "Setup could not save the report. Select Save report again.",
    "s05_done_no_restart": "Virtual Machine Platform and Windows Subsystem for Linux (WSL) are "
    "ready on this PC.",
    "s12_fail1": "load the Slate Operations programs",
    "s12_fail2": "create the settings and passwords",
    "s05_done_vmp": "Setup turned on Virtual Machine Platform. Windows finishes it when this PC "
    "restarts.",
    "s05_done_wsl": "Setup installed Windows Subsystem for Linux (WSL). Windows finishes it when "
    "this PC restarts.",
    "s05_done_pending": "Virtual Machine Platform is already turned on. Windows finishes it when "
    "this PC restarts.",
    "s05_subtitle_vmp": "Windows finishes Virtual Machine Platform when this PC restarts.",
    "s05_subtitle_wsl": "Windows finishes Windows Subsystem for Linux (WSL) when this PC restarts.",
    "s05_subtitle_ready": "This PC does not need a restart.",
}


class W14RecheckTest(unittest.TestCase):
    """W14 re-check round (TASK-0097, AC-1 to AC-9): the BLOCKING findings of the QA, Software
    Architect, Product Designer and Security Engineer reviews of b8d55ffe..2a6d5762. The
    PowerShell cases and the [Code] self-test prove the behavior on the Windows runner; these
    checks hold the wiring that a static read can see."""

    def setUp(self) -> None:
        self.raw = pascal_code()
        self.selftest = SELFTEST.read_text(encoding="ascii")

    def part(self, head: str) -> str:
        self.assertIn(head, self.raw)
        return routine(self.raw, head)

    def test_w14_d10_an_outlook_address_hides_every_other_field(self) -> None:
        # Owner on rc.24: with an Outlook.com address, the User name box of the Other fields
        # stayed at its build position at the top of S09, as an unlabeled empty field.
        hide = self.part("procedure HideMailOtherFields;")
        for name in (
            "MailServerLabel",
            "MailServer",
            "MailPortLabel",
            "MailPort",
            "MailSecurityLabel",
            "MailSsl",
            "MailStartTls",
            "MailUserLabel",
            "MailUser",
        ):
            with self.subTest(name=name):
                self.assertIn(f"{name}.Visible := False;", hide)
        layout = self.raw.split("procedure LayoutMail;\nvar", 1)[1]
        outlook = layout.split("if MailOutlook and not Other then", 1)[1].split("  else\n", 1)[0]
        self.assertIn("HideMailOtherFields;", outlook)
        self.assertIn(
            "'W14-D10 S09 Outlook address hides the password and the Other fields'", self.selftest
        )

    def test_ac_2_receive_through_the_task_layout_reads_the_data_folder(self) -> None:
        # Architect U-1: exec.ps1 builds the layout with no data root, so receive joined an
        # empty payload path. receive now sets the data root as the Windows-side jobs do.
        exec_lib = (SCRIPTS / "lib/Exec.ps1").read_text(encoding="ascii")
        receive = exec_lib.split("if ($job -eq 'receive') {", 1)[1].split("foreach ($name", 1)[0]
        self.assertIn("$state = Read-InstallState -Layout $Layout", receive)
        self.assertIn("Set-LayoutDataRoot -Layout $Layout -DataRoot $state.data_root", receive)
        tests = (PS_TESTS / "Exec.Tests.ps1").read_text(encoding="ascii")
        self.assertIn("Test-Case 'AC-2 U-1 ", tests)
        case = tests.split("Test-Case 'AC-2 U-1 ", 1)[1].split("\nTest-Case ", 1)[0]
        self.assertRegex(case, r"New-SlateOpsLayout -StateRoot [^\n]*\)\n")
        self.assertNotIn(
            "New-SlateOpsLayout -StateRoot (Join-Path $root 'ProgramData\\SlateOps') -DataRoot",
            case,
        )
        self.assertIn("'receive'", case)

    def test_ac_3_no_background_step_starts_during_a_close_flow(self) -> None:
        # Architect N-1: the removal never meets a new server part job. Comments removed: the
        # gate is the first statement.
        poll = code_only(self.part("procedure PollBackground;"))
        self.assertRegex(
            poll, r"(?s)begin\s+if CloseFlowRunning then\s+Exit;\s+if PollBgPending then"
        )

    def test_ac_4_only_the_password_error_moves_into_the_password_column(self) -> None:
        # Designer B1: every error moved to the right half and lost its last lines.
        layout = self.part("procedure LayoutMail;\nvar")
        self.assertRegex(
            layout,
            r"if MailErrorAfter = MailPassword then\s+MailError\.SetBounds\(Half \+ ScaleX\(16\)",
        )
        self.assertIn(
            "SelfRecord('AC-4 S09 Other: the server error is under its field, full width'",
            self.selftest,
        )

    def test_ac_5_m01_repair_shows_its_progress_in_place_of_the_actions(self) -> None:
        # Designer B2 (option a): the 7-stage block replaced the 8-action grid while Repair runs.
        render = self.part("procedure RenderMaint;\nvar")
        self.assertRegex(
            render,
            r"if StepFor = 'repair' then\s+AddProgress\('repair'[^\n]*\n\s+else\s+begin\s+"
            r"CurY := CurY \+ ScaleY\(4\);\s+for I := 0 to 3 do",
        )
        self.assertIn("SelfDraw('AC-5 M01 Repair running', P_MAINT);", self.selftest)

    def test_ac_6_s05_says_what_setup_did_and_shows_the_installed_wsl(self) -> None:
        # Designer non-blocking 1 to 3 (parent: blocking): the verdict and subtitle follow the
        # helper codes; the no-restart state has no restart stage; a present WSL shows its own
        # version.
        copy = read_copy()
        for key in (
            "s05_done_vmp",
            "s05_done_wsl",
            "s05_done_pending",
            "s05_subtitle_vmp",
            "s05_subtitle_wsl",
            "s05_subtitle_ready",
        ):
            with self.subTest(key=key):
                self.assertEqual(copy.get(key), RECHECK_COPY[key])
        render = self.part("procedure RenderRestart;")
        self.assertIn("AddVerdict(CM(S05VerdictKey(PrepFeature, PrepWsl)));", render)
        self.assertIn("WizardForm.PageDescriptionLabel.Caption := CM(S05SubtitleKey);", render)
        self.assertIn("else if not Vmp and not Wsl then Result := 's05_subtitle_ready'", self.raw)
        self.assertIn("'AC-6 S05 subtitle with no restart'", self.selftest)
        self.assertIn(
            "WizardForm.PageDescriptionLabel.Caption := CM('s05_subtitle_ready');", render
        )
        self.assertIn("AddProgress('prep', S05NoRestartStages, 3, '', 0);", render)
        self.assertIn("FM3('s05_details', S05WslVersion, PrepFeature, PrepWsl)", render)
        self.assertIn("StepText('pc', Key, S05WslVersion, '', '')", self.raw)
        for check in (
            "'AC-6 S05 verdict enabled_now installed'",
            "'AC-6 S05 verdict enabled_now present'",
            "'AC-6 S05 verdict enabled installed'",
            "'AC-6 S05 verdict pending present'",
            "'AC-6 S05 subtitle before the work'",
            "'AC-6 S05 subtitle after the work'",
            "'AC-6 S05 installed WSL version'",
            "'AC-6 S05 no restart: 4 stages, at 3'",
        ):
            with self.subTest(check=check):
                self.assertIn(f"SelfRecord({check}", self.selftest)

    def test_ac_7_copy_strings_and_no_bitlocker_suggestion(self) -> None:
        copy = read_copy()
        for key in (
            "report_failed",
            "s05_done_no_restart",
            "s12_fail1",
            "s12_fail2",
        ):
            with self.subTest(key=key):
                self.assertEqual(copy.get(key), RECHECK_COPY[key])
        # DEC-0037: setup never suggests BitLocker; C24 "off" has no message to look up.
        self.assertNotIn("c24_off", copy)
        message = self.part("function ItemMessage(Item: TCheckItem): String;")
        self.assertLess(
            message.index("(Item.Id = 'C24') and (Item.Code = 'off')"),
            message.index("Key := Lowercase(Item.Id) + '_' + Item.Code;"),
        )

    def test_ac_8_one_line_texts_have_one_full_stop(self) -> None:
        # Designer 4 and 9: "D:. · 2:10", and a status line of 18 px that a long step wraps.
        self.assertIn("function NoStop(Text: String): String;", self.raw)
        self.assertIn(
            "NoStop(Action)",
            self.part(
                "function OneLine(Number, Total: Integer; Action: String; Since: Cardinal): String;"
            ),
        )
        # DEC-0041: the status line is gone (no background before Install, no close flow line).
        self.assertNotIn("StatusLine", self.raw)

    def test_ac_9_the_report_zips_only_a_collected_report(self) -> None:
        # Security S97-1: after the collect limit, the password drop and the zip ran while
        # report-collect could still write.
        poll = self.part("procedure PollReport;")
        collect = poll.split("if ReportPhase = 'collect' then", 1)[1]
        self.assertRegex(collect, r"(?s)if Code <> 'collected' then.*DropFilesWithPassword\(")
        failed = collect.split("if Code <> 'collected' then", 1)[1].split("end;", 1)[0]
        self.assertIn("EndReport", failed)
        self.assertNotIn("report-zip", failed)
        self.assertIn("ReportLine := CM('report_failed');", self.part("procedure EndReport;"))


class Dec0041Test(unittest.TestCase):
    """DEC-0041 (TASK-0097): setup is a complete installation or nothing, with no email page.
    AC-W1 to AC-W8 as a static read can hold them; the PowerShell cases (Removal.Tests.ps1) and
    the [Code] self-test prove the behavior on the Windows runner."""

    def setUp(self) -> None:
        self.raw = pascal_code()
        self.selftest = SELFTEST.read_text(encoding="ascii")
        self.helper = (SCRIPTS / "setup-helper.ps1").read_text(encoding="ascii")
        self.removal = (
            (PS_TESTS / "Removal.Tests.ps1").read_text(encoding="ascii")
            if (PS_TESTS / "Removal.Tests.ps1").is_file()
            else ""
        )

    def part(self, head: str) -> str:
        self.assertIn(head, self.raw)
        return routine(self.raw, head)

    def test_ac_w1_setup_has_no_email_page_and_no_server_work_before_install(self) -> None:
        skip = self.part("function ShouldSkipPage(PageID: Integer): Boolean;")
        self.assertIn(
            "if (PageID = Pages[P_MAINT].ID) or (PageID = Pages[P_EMAIL].ID) then Result := True",
            skip,
        )
        for gone in ("ContinueLater", "AskCancelChoice", "BgResume", "StatusLine", "MailLater"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, self.raw)
        # S07 Next only checks the folder; the data folder and the server part start on S12.
        nxt = self.part("function NextButtonClick(CurPageID: Integer): Boolean;")
        data = nxt.split("else if CurPageID = Pages[P_DATA].ID then", 1)[1].split("else if", 1)[0]
        self.assertIn("StartDataCheck;", data)
        self.assertNotIn("prepare-data", self.part("procedure StartDataCheck;"))
        self.assertIn("'data-check'", self.helper)
        self.assertEqual(len(re.findall(r"(?m)^\s+StartServerPrep;", self.raw)), 1)
        changed = self.part("procedure CurPageChanged(CurPageID: Integer);")
        install = changed.split("else if CurPageID = Pages[P_INSTALL].ID then", 1)[1]
        self.assertIn("StartServerPrep;", install.split("RenderInstall;", 1)[0])
        self.assertNotIn(
            "StartBackground", self.part("procedure TimerTick(H, Msg, Id, Tick: Longword);")
        )
        self.assertIn("Test-Case 'AC-W1 S07 checks the chosen data folder", self.removal)

    def test_ac_w1_s08_asks_the_admin_and_a_password_and_s11_names_the_sign_in_address(
        self,
    ) -> None:
        build = self.part("procedure BuildOrgPage;")
        for field in (
            "OrgName :=",
            "OrgYourName :=",
            "OrgEmail :=",
            "OrgPassword :=",
            "OrgConfirm :=",
        ):
            with self.subTest(field=field):
                self.assertIn(field, build)
        self.assertIn("OrgPassword.PasswordChar := '*';", build)
        self.assertIn("OrgConfirm.PasswordChar := '*';", build)
        self.assertIn("OrgShow.OnClick := @OrgShowClick;", build)
        check = self.part("function CheckOrg: Boolean;")
        self.assertIn("if not ValidEmail(Trim(OrgEmail.Text)) then", check)
        self.assertIn("if PasswordProblem(OrgPassword.Text) <> '' then", check)
        self.assertIn("if OrgConfirm.Text <> OrgPassword.Text then", check)
        # R-2: the rule of the install job and bootstrap (engine invitation.valid_password):
        # 12 characters (code points) to 72 UTF-8 bytes, no control character.
        rule = self.part("function PasswordProblem(S: String): String;")
        self.assertIn("if (Chars < 12) or (Chars > 72) then", rule)
        self.assertIn("else if Bytes > 72 then", rule)
        self.assertIn("(Code >= $D800) and (Code <= $DBFF) then Bytes := Bytes + 4", rule)
        engine = (ROOT / "packaging/engine/invitation.py").read_text()
        self.assertIn("PASSWORD_MIN_CHARACTERS, PASSWORD_MAX_BYTES = 12, 72", engine)
        copy = read_copy()
        self.assertEqual(copy.get("s11_admin"), "Administrator: %1. You sign in with this address.")
        self.assertNotIn("s11_mail", self.part("procedure RenderReady;"))
        # Parent decision (S08 too tall): Password and its second entry share one row; "Show" sits
        # at the right end of the Password label's line (spec 6.1 rule 9 exception).
        layout = self.part("procedure LayoutOrg;\nvar")
        self.assertIn("OrgPassword.SetBounds(0, Y, Half, OrgPassword.Height);", layout)
        self.assertIn(
            "OrgConfirm.SetBounds(Half + ScaleX(16), Y, Half, OrgConfirm.Height);", layout
        )
        self.assertIn("OrgShow.SetBounds(Half - ShowWidth, Y, ShowWidth, OrgShow.Height);", layout)
        self.assertIn(
            "SelfRecord('AC-W1 S08 fields in order, Password and its second entry in one row, Show "
            "on the password line, the error inside the page', Ok,",
            self.selftest,
        )
        # Windows CI on 53acdd6e: a masked field is any character but 0 (themed edit controls
        # draw a dot), and each S08 check says what it saw.
        show = self.selftest.split("SelfRecord('AC-W1 S08 Show shows both passwords", 1)[1]
        self.assertIn("'shown chars ' + Masked", show.split(");", 1)[0])
        self.assertNotIn("EditPasswordChar(OrgPassword) = Ord('*')", self.selftest)

    def test_ac_w2_every_server_step_runs_on_s12_in_order_with_a_limit(self) -> None:
        prep = self.part("procedure PollServerPrep;")
        self.assertLess(prep.index("DataPrepared := True;"), prep.index("StartBackground;"))
        self.assertLess(prep.index("PollBackground;"), prep.index("InstallStep := 0;"))
        self.assertIn("InstallFailAt(CM('s12_stage_data'), PrepFailText(Code));", prep)
        self.assertIn("if (Code = '') and (Elapsed(DataStartedAt) > DATA_LIMIT_MS) then", prep)
        stages = self.part("function S12Stages: String;")
        self.assertIn("Result := CM('s12_stage_data') + '|' + BgStageNames;", stages)
        step_names = self.part("function BgStepName(Index: Integer): String;")
        names = re.findall(r"[0-6]: Result := '([a-z-]+)';", step_names)
        self.assertEqual(
            names,
            [
                "service",
                "wslconfig",
                "import-distro",
                "start-boot",
                "receive",
                "prepare",
                "prefetch",
            ],
        )
        # The install job ends at its limit (only M05's update keeps no limit, Preserved).
        poll = self.part("procedure PollJob;")
        self.assertIn(
            "if (JobPurpose <> 'update') and (Elapsed(JobStartedAt) > JobLimitMs) then", poll
        )
        self.assertIn(
            "StartJob('install', Answers, 'install', True, True, INSTALL_JOB_MINUTES);", self.raw
        )
        install = self.part("procedure PollInstall;")
        self.assertIn(
            "else if Code = 'job_timeout' then InstallFail(0, CM('s12_step_limit'))", install
        )
        self.assertIn("(Elapsed(InstallOutAt) > INSTALL_STEP_MS)", install)
        self.assertNotIn("InstallSlow", self.raw)
        self.assertIn(
            "SelfRecord('AC-W2 S12 lists every stage and stands at the server part step'",
            self.selftest,
        )

    def test_ac_w3_cancel_close_and_a_failed_install_remove_everything_with_limits(self) -> None:
        cancel = self.part(
            "procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);"
        )
        self.assertRegex(cancel, r"RunRemoval\('close'\);\s+Cancel := True;\s+end;")
        nxt = self.part("function NextButtonClick(CurPageID: Integer): Boolean;")
        failed = nxt.split("if InstallFailed then", 1)[1].split("end", 1)[0]
        self.assertIn("if ReportPhase <> '' then", failed)
        self.assertRegex(
            failed, r"RunRemoval\('close'\);\s+ForceClose := True;\s+WizardForm\.Close;"
        )
        self.assertIn("SetNextCaption(CM('s13_remove'));", self.part("procedure RenderInstall;"))
        flow = self.part("procedure PollCloseFlow;\nvar")
        order = [
            flow.index(
                "CloseStep(2, 'stop', CM('remove_stopping'), 'uninstall-stop', '', REMOVE_STEP_MS)"
            ),
            flow.index(
                "CloseStep(3, 'data', CM('remove_data_line'), 'setup-remove-data', '', "
                "REMOVE_DATA_MS)"
            ),
            flow.index(
                "CloseStep(4, 'features', CM('remove_features'), 'remove-features', '', "
                "REMOVE_FEATURES_MS)"
            ),
            flow.index(
                "CloseStep(5, 'windows', CM('remove_windows'), 'remove-windows', Extra, "
                "REMOVE_WINDOWS_MS)"
            ),
        ]
        self.assertEqual(order, sorted(order))
        self.assertIn("EndCloseFlow('limit');", flow)
        self.assertIn("EndCloseFlow('kept');", flow)
        self.assertIn("REMOVE_STEP_MS = 20000;", self.raw)
        self.assertIn(
            "CloseStep(1, 'job', CM('remove_job'), 'job-stop', '', REMOVE_STEP_MS);",
            self.part("procedure StartCloseFlow(Flow, After: String);\nbegin"),
        )
        # The removal runs from the timer ahead of the gates, never from inside a tick.
        tick = self.part("procedure TimerTick(H, Msg, Id, Tick: Longword);")
        self.assertLess(
            tick.index("if RemoveForm <> nil then"), tick.index("if not WizardReady then")
        )
        self.assertNotIn("RunRemoval(", tick)
        self.assertIn("'setup-remove-data', 'remove-features'", self.helper)
        uninstall = (SCRIPTS / "lib/Uninstall.ps1").read_text(encoding="ascii")
        features = uninstall.split("function Remove-SetupFeatures {", 1)[1].split("\nfunction ", 1)[
            0
        ]
        self.assertIn("-ceq 'none'", features)
        self.assertIn("-ine $SlateOps.DistroName", features)
        for case in (
            "AC-W3 WSL that was on the PC before setup stays",
            "AC-W3 WSL that setup installed stays while another distribution is registered",
            "AC-W3 WSL and Virtual Machine Platform that setup turned on go when no other "
            "distribution is registered, with no restart",
            "AC-W3 a distribution check that fails or is unclear keeps WSL and Virtual Machine "
            "Platform",
            "AC-W3 the setup removal never deletes kept data",
        ):
            with self.subTest(case=case):
                self.assertIn(f"Test-Case '{case}", self.removal)
        self.assertIn(
            "SelfRecord('AC-W3 the removal never holds the window, every step has its limit, and "
            "it ends'",
            self.selftest,
        )

    def test_ac_w4_an_earlier_unfinished_run_is_removed_at_start(self) -> None:
        windows = (SCRIPTS / "lib/Windows.ps1").read_text(encoding="ascii")
        entry = windows.split("function Get-SetupEntry {", 1)[1].split("\nfunction ", 1)[0]
        self.assertIn("return @{ screen = 'S01'; next = ''; cleanup = $true }", entry)
        self.assertNotIn("continue_later", entry)
        self.assertIn("-Leftover:(Test-SetupLeftover -Layout $layout)", self.helper)
        start = self.part("function InitializeSetup(): Boolean;")
        self.assertIn(
            "EntryCleanup := (Pos('\"cleanup\":true', Text) > 0) and not StateUnsafe", start
        )
        changed = self.part("procedure CurPageChanged(CurPageID: Integer);")
        welcome = changed.split("if CurPageID = wpWelcome then", 1)[1]
        self.assertLess(welcome.index("RunRemoval('start')"), welcome.index("CM('s01_title')"))
        self.assertIn(
            "Test-Case 'AC-W4 an earlier run that did not finish is removed at start", self.removal
        )

    def test_ac_w5_the_install_job_gets_the_admin_password_through_the_pipe_only(self) -> None:
        job = self.part("procedure InstallStartJob(TimeZone: String);")
        self.assertIn("'\"admin_password\":' + JsonText(OrgPassword.Text)", job)
        self.assertLess(job.index("'},' +"), job.index('"admin_password"'))
        self.assertIn('"admin_email"', job)
        self.assertIn('"admin_username"', job)
        # No email server key (DEC-0041: email is set up later, in M02).
        self.assertNotRegex(job, r'(?i)smtp|"(host|port|user|password|sender_email|sender_name)"')
        self.assertIn("StartJob('install', Answers, 'install', True, True,", job)
        # The channel self-test and R7 come first, as M02 runs them before the email password.
        check = self.part("procedure InstallChannelCheck(TimeZone: String);")
        self.assertIn("StartJob('pipe-test', Value, 'selftest:'", check)
        finished = self.part("procedure StepFinished(ForTag, Code: String);\nvar")
        r7 = finished.split("else if ForTag = 'inst-r7' then", 1)[1].split("else if ForTag", 1)[0]
        self.assertIn("if Code = 'clear' then InstallStartJob(InstallTz)", r7)
        for line in re.findall(r"(?m)^.*\bLog\(.*$", self.raw):
            with self.subTest(line=line.strip()):
                self.assertNotIn("OrgPassword", line)
        self.assertIn("DropFilesHolding(Staging, OrgPassword.Text);", self.raw)
        self.assertNotIn("SetPreviousData(", self.raw)

    def test_ac_w6_m02_offers_gmail_and_other_and_says_where_the_test_went(self) -> None:
        self.assertNotIn("MailM365", self.raw)
        copy = read_copy()
        self.assertFalse([key for key in copy if "m365" in key])
        self.assertEqual(
            copy.get("s09_outlook"),
            "Outlook.com accounts cannot send email for Slate Operations. Use a Gmail account, "
            "or the mail server of another email provider.",
        )
        self.assertEqual(
            copy.get("m02_test_sent"),
            "Slate Operations sent a test email to %1. Check that inbox and its Spam folder.",
        )
        mail = self.part("procedure PollMail;")
        self.assertRegex(
            mail,
            r"if JobCode = 'smtp_passed' then\s+begin[^;]*;?\s*MailPassed := True;"
            r"\s+StartSetEmail;",
        )
        self.assertIn(
            "else if MailSaved and (MailSentTo <> '') then MailStatus.Caption := "
            "FM1('m02_test_sent', MailSentTo)",
            self.part("procedure RenderMailStatus;"),
        )
        # sent_to comes through the pipe (smtp-test is a pipe-output job), never from a file.
        self.assertIn("MailSentTo := JsonValue(JobText, 'sent_to');", mail)
        self.assertRegex(self.raw, r"StartJob\('smtp-test', [^;]*'smtp', True, True, 3\);")
        exec_lib = (SCRIPTS / "lib/Exec.ps1").read_text(encoding="ascii")
        self.assertIn(
            "PipeOutputJobs = @('install', 'new-recovery-key', 'pipe-test', 'smtp-test')", exec_lib
        )
        # M01: "Email: not set up" from the status flag only; the admin address stays out.
        self.assertEqual(
            copy.get("m01_email_not_set"),
            "Email is not set up, so Slate Operations cannot send invitations or password resets. "
            "Select Set up email.",
        )
        render = self.part("procedure RenderMaint;\nvar")
        self.assertRegex(
            render,
            r"if \(MaintStatus = 'ok'\) and MaintEmailMissing then\s+"
            r"AddText\(CM\('m01_email_not_set'\), False\);",
        )
        self.assertIn(
            "MaintEmailMissing := JsonLiteral(Text, 'email_configured') = 'false';", self.raw
        )
        uninstall = (SCRIPTS / "lib/Uninstall.ps1").read_text(encoding="ascii")
        status = uninstall.split("function Get-EngineStatus {", 1)[1].split("\nfunction ", 1)[0]
        self.assertIn("$values.email_configured = $email", status)
        self.assertNotIn("'admin_email'", status)
        self.assertIn("finally { Remove-EngineOutput -Layout $Layout -Result $result }", status)
        start = (SCRIPTS / "start.ps1").read_text(encoding="ascii")
        self.assertIn(
            "if (Test-Path -LiteralPath $stdout) { Remove-PathNoFollow -Path $stdout }", start
        )
        for line in re.findall(r"(?m)^.*\bLog\(.*$", self.raw):
            with self.subTest(line=line.strip()):
                self.assertNotIn("MailSentTo", line)
        self.assertIn("SelfRecord('AC-W6 M02 says where the test email went'", self.selftest)
        self.assertIn("HideMailOtherFields;", self.part("procedure LayoutMail;\nvar"))

    def test_ac_w7_no_wait_without_a_limit_and_no_focus_box_on_links(self) -> None:
        for path in (WIZARD, MAINTENANCE):
            text = path.read_text(encoding="ascii")
            for match in re.finditer(r"(\w+) := TNewLinkLabel\.Create\(WizardForm\);", text):
                with self.subTest(link=match.group(1)):
                    after = text[match.end() : match.end() + 200]
                    self.assertIn(f"NoFocusBox({match.group(1)});", after)
        self.assertIn(
            "Link.TabStop := False;", self.part("procedure NoFocusBox(Link: TNewLinkLabel);")
        )
        uninstall = UNINSTALL.read_text(encoding="ascii")
        run = routine(
            uninstall, "function URun(Action, ARunId, Extra: String; LimitSec: Integer): String;"
        )
        self.assertIn("SW_HIDE, ewNoWait, Code);", run)
        self.assertIn("(GetTickCount - Started) < Cardinal(LimitSec * 1000)", run)
        calls = re.findall(r"URun\('[a-z-]+', [^;]*", uninstall)
        self.assertEqual(len(calls), 7)
        for call in calls:
            with self.subTest(call=call):
                self.assertRegex(call, r"U_[A-Z]+_SEC\)")
        self.assertIn("SelfRecord('AC-W7 link labels draw no focus box'", self.selftest)

    def test_ac_w8_a_job_ends_at_its_limit_even_when_its_result_is_seen(self) -> None:
        poll = self.part("procedure PollJob;")
        self.assertNotIn("(not Found) and (JobPurpose", poll)
        self.assertIn(
            "Log('Job ' + JobName + ': the job-result helper answered ' + Code + '.');", poll
        )
        self.assertIn("SelfJobLimit;", routine(self.selftest, "procedure RunSelfTest;"))
        self.assertIn(
            "SelfRecord('AC-W8 a handover that job-result never confirms ends at the job limit "
            "with its message'",
            self.selftest,
        )
        # The resume's unpacking (no limit, dropped by a close flow) is gone with DEC-0041.
        for gone in ("StartBgPrep", "PollBgPrep", "'resume-unpack'"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, self.raw)

    def test_ac_w9_a_restart_that_setup_asked_for_continues_and_removes_nothing(self) -> None:
        windows = (SCRIPTS / "lib/Windows.ps1").read_text(encoding="ascii")
        entry = windows.split("function Get-SetupEntry {", 1)[1].split("\nfunction ", 1)[0]
        self.assertIn("if ($stage -eq 'check_restart') {", entry)
        self.assertIn("return @{ screen = 'S02'; next = ''; welcome_back = $true }", entry)
        self.assertLess(
            entry.index("if ($stage -eq 'check_restart') {"), entry.rindex("cleanup = $true")
        )
        self.assertIn("if ($Prepared) { $marks.prepared = $true }", self.helper)
        restart = self.part("procedure CheckRestart(Index: Integer);")
        self.assertIn("if (PrepState <> '') or (EntryNext = 'S07') then", restart)
        self.assertIn("Extra := Extra + ' -Prepared';", restart)
        start = self.part("function InitializeSetup(): Boolean;")
        self.assertIn("EntryWelcomeBack := Pos('\"welcome_back\":true', Text) > 0;", start)
        skip = self.part("function ShouldSkipPage(PageID: Integer): Boolean;")
        self.assertIn("Result := Resumed or EntryWelcomeBack", skip)
        self.assertIn("EntryWelcomeBack", self.part("function SetupChangedPc: Boolean;"))
        self.assertIn("Test-Case 'AC-W9 a restart that setup asked for continues", self.removal)


def block_balance_problems(text: str) -> list[str]:
    """Routine-level block balance of Pascal [Code]: every begin, case, try and record has its
    end, no end comes without an opener, and each routine heading at the start of a line starts
    at depth 0. Comments and strings are removed first (code_only); ISPP lines (#) and the
    ; comment lines before [Code] are skipped, so line numbers are the file's."""
    problems: list[str] = []
    depth = 0
    for number, line in enumerate(code_only(text).splitlines(), start=1):
        if line.lstrip().startswith(("#", ";")):
            continue
        if re.match(r"(procedure|function) ", line) and depth != 0:
            problems.append(f"line {number}: routine starts at depth {depth}")
            depth = 0
        for word in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", line):
            lower = word.lower()
            if lower in ("begin", "case", "try", "record"):
                depth += 1
            elif lower == "end":
                depth -= 1
                if depth < 0:
                    problems.append(f"line {number}: end without an opener")
                    depth = 0
    if depth != 0:
        problems.append(f"end of file at depth {depth}")
    return problems


class PascalBlockBalanceTest(unittest.TestCase):
    """Windows CI on 4dcbfada: "Error on line 1715 in Wizard.iss: Column 4: period ('.')
    expected", a stray end; after DropFilesWithPassword. The strict scan checked names, not
    blocks; this holds the blocks of every [Code] file."""

    def test_every_code_file_has_balanced_blocks(self) -> None:
        for path in (*CODE_FILES, SELFTEST):
            with self.subTest(path=path.name):
                self.assertEqual(block_balance_problems(path.read_text(encoding="ascii")), [])

    def test_no_form_sets_a_modal_result(self) -> None:
        # Windows CI on ddd21fb5: "Unknown identifier 'MODALRESULT'" at RemoveForm.ModalResult.
        # Inno's Pascal Script gives TSetupForm no ModalResult; only buttons have one.
        code = code_only(pascal_code() + SELFTEST.read_text(encoding="ascii"))
        self.assertEqual(re.findall(r"\b\w*Form\.ModalResult\b", code), [])
        self.assertIn("RemoveForm.Close", routine(pascal_code(), "procedure EndCloseFlow("))

    def test_no_code_reads_a_char_property(self) -> None:
        # Windows CI on 2d290ced: "Could not call proc". Pascal Script reaches PasswordChar
        # through RTTI; the setter takes a Char, the getter has no Char case (uPSRuntime.pas
        # ClassCallProcProperty, Inno 6.7.4), so the property can be written, never read.
        code = code_only(pascal_code() + SELFTEST.read_text(encoding="ascii"))
        self.assertEqual(re.findall(r"\.PasswordChar\b(?!\s*:=)", code), [])

    def test_the_balance_check_finds_a_stray_end_and_a_missing_end(self) -> None:
        good = "[Code]\nprocedure A;\nbegin\n  case X of\n    1: begin end;\n  end;\nend;\n"
        self.assertEqual(block_balance_problems(good), [])
        stray = good + "end;\nprocedure B;\nbegin\nend;\n"
        self.assertEqual(block_balance_problems(stray), ["line 8: end without an opener"])
        missing = "[Code]\nprocedure A;\nbegin\n  try\n  finally\nend;\nprocedure B;\n"
        self.assertEqual(block_balance_problems(missing), ["line 7: routine starts at depth 1"])


class Dec0039Test(unittest.TestCase):
    """DEC-0039 (TASK-0097): the address for PCs and phones is <label>.local, the label from the
    S08 short name; our own mDNS responder in the boot task's process answers for it (option B;
    the CI mdns-spike showed Windows' responder never answers for a registered name); one
    inbound UDP 5353 rule; C15 and C30 go. Behavior: Address.Tests.ps1 and the self-test."""

    def setUp(self) -> None:
        self.raw = pascal_code()
        self.selftest = SELFTEST.read_text(encoding="ascii")
        self.helper = (SCRIPTS / "setup-helper.ps1").read_text(encoding="ascii")
        self.windows = (SCRIPTS / "lib/Windows.ps1").read_text(encoding="ascii")
        mdns = SCRIPTS / "lib/Mdns.ps1"
        self.mdns = mdns.read_text(encoding="ascii") if mdns.is_file() else ""
        tests = PS_TESTS / "Address.Tests.ps1"
        self.tests = tests.read_text(encoding="ascii") if tests.is_file() else ""

    def part(self, head: str) -> str:
        self.assertIn(head, self.raw)
        return routine(self.raw, head)

    def test_ac_a1_s08_short_name_makes_the_address_and_next_checks_the_network(self) -> None:
        build = self.part("procedure BuildOrgPage;")
        self.assertIn("OrgSlug := NewEditAt(Surface, 0); OrgSlug.MaxLength := 63;", build)
        self.assertIn("NoFocusBox(OrgAddressLink);", build)
        label = self.part("function LabelFromName(Name: String): String;")
        self.assertIn("if Length(Result) > 30 then", label)
        check = self.part("function CheckOrg: Boolean;")
        self.assertIn("if not ValidLabel(OrgSlug.Text) then", check)
        self.assertLess(
            check.index("RunStep('name-check', '-Label ' + OrgSlug.Text, 'org-name'"),
            check.index("HostName := OrgSlug.Text;"),
        )
        finished = self.part("procedure StepFinished(ForTag, Code: String);\nvar")
        name = finished.split("else if ForTag = 'org-name' then", 1)[1].split("else if ForTag", 1)[
            0
        ]
        self.assertIn("if Code = 'in_use' then", name)
        self.assertIn("FM1('s08_err_label_in_use', OrgSlug.Text + '.local')", name)
        # The helper's name check reads the network only (P-3 a: a check, no work).
        action = self.helper.split("'name-check' {", 1)[1].split("\n        }\n", 1)[0]
        self.assertIn("Test-MdnsNameInUse -Name $Label", action)
        self.assertNotRegex(action, r"Write-JsonFile|Save-|Set-|New-Item")
        self.assertIn("[ValidatePattern('^$|^[a-z0-9]+(-[a-z0-9]+)*$')][string]$Label", self.helper)
        copy = read_copy()
        self.assertEqual(
            copy.get("s08_address_line"), "Address for PCs and phones: https://%1.local"
        )
        self.assertIn(
            "SelfRecord('AC-A1 S08 address line from the organization name'", self.selftest
        )
        self.assertIn("Test-Case 'AC-A1 the address label follows", self.tests)

    def test_ac_a2_every_use_of_the_address_reads_the_stored_label(self) -> None:
        for gone in ("DnsHostName", "GetComputerNameEx"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, self.raw)
        self.assertIn('Filename: "https://{code:AddressHost}"', ISS.read_text(encoding="ascii"))
        start = self.part("function InitializeSetup(): Boolean;")
        self.assertRegex(
            start,
            r"if \(EntryNext = 'S14'\) or \(EntryScreen = 'M01'\) or \(EntryScreen = 'M05'\) then"
            r"\s+HostName := StoredAddressLabel;",
        )
        self.assertIn("' -Label ' + HostName", self.part("procedure StartDataFolder;"))
        self.assertIn("',\"public_host\":' + JsonText(HostName + '.local')", self.raw)
        self.assertIn("$state['host_label'] = $Label", self.windows)
        lib = "\n".join(
            (SCRIPTS / name).read_text(encoding="ascii")
            for name in ("setup-helper.ps1", "start.ps1", "lib/Windows.ps1", "lib/Uninstall.ps1")
        )
        self.assertNotIn("DNSHostName", lib)
        self.assertEqual(lib.count("Get-InstallAddressLabel -Layout"), 4)
        self.assertIn("Test-Case 'AC-A2 the stored label comes from install.json", self.tests)

    def test_ac_a3_our_responder_runs_in_the_boot_task_process(self) -> None:
        start = (SCRIPTS / "start.ps1").read_text(encoding="ascii")
        self.assertIn("'Common', 'Checks', 'Exec', 'Mdns'", start)
        self.assertIn("Start-MdnsResponderThread -Label $label", start)
        for value in (
            "RecheckMs      = 60000",
            "ProbeCount     = 3",
            "AnnounceCount  = 2",
            "Group          = '224.0.0.251'",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.mdns)
        thread = self.mdns.split("function Start-MdnsResponderThread {", 1)[1]
        self.assertIn("[PowerShell]::Create()", thread)
        self.assertIn("Write-RunLog 'boot.mdns'", thread)
        loop = self.mdns.split("function Invoke-MdnsResponder {", 1)[1].split("\nfunction ", 1)[0]
        for log in re.findall(r"& \$Log [^\n]*", loop):
            with self.subTest(log=log):
                self.assertNotIn("remote", log)
        for case in (
            "AC-A3 the responder probes three times, announces twice, then answers a query",
            "AC-A3 the responder re-checks the adapter every minute",
            "AC-A3 a conflict during probing",
        ):
            with self.subTest(case=case):
                self.assertIn(f"Test-Case '{case}", self.tests)

    def test_ac_a4_one_mdns_rule_recorded_so_every_removal_deletes_it(self) -> None:
        definition = self.windows.split("function Get-FirewallRuleDefinition {", 1)[1].split(
            "\nfunction ", 1
        )[0]
        self.assertIn("Mdns = @{", definition)
        rule = definition.split("Mdns = @{", 1)[1].split("}", 1)[0]
        for field in (
            "Direction = 'Inbound'",
            "Action = 'Allow'",
            "Protocol = 'UDP'",
            "LocalPort = '5353'",
            "Profile = 'Private'",
            "RemoteAddress = 'LocalSubnet'",
            "Program = (Join-Path $SlateOpsPaths.System32 "
            "'WindowsPowerShell\\v1.0\\powershell.exe')",
        ):
            with self.subTest(field=field):
                self.assertIn(field, rule)
        self.assertIn(
            "$record['firewall_rules'] = @(Get-FirewallRecordNames -Definition $definition)",
            self.windows,
        )
        uninstall = (SCRIPTS / "lib/Uninstall.ps1").read_text(encoding="ascii")
        self.assertIn(
            "foreach ($name in @(Get-DictValue $record 'firewall_rules')) { if ($name) { "
            "Get-NetFirewallRule -Name $name",
            uninstall,
        )
        self.assertIn("Test-Case 'AC-A4 the mDNS rule allows inbound UDP 5353", self.tests)

    def test_ac_a5_c15_and_c30_are_gone_and_c16_moved_to_s08(self) -> None:
        checks = (SCRIPTS / "lib/Checks.ps1").read_text(encoding="ascii")
        for gone in (
            "function Test-C15",
            "function Test-C16",
            "function Test-C30",
            "FactoryNamePattern",
        ):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, checks)
        self.assertFalse([key for key in read_copy() if re.match(r"c(15|16|30)_", key)])
        self.assertNotRegex(code_only(self.raw), r"'C(15|16|30)'")
        stage = self.part("function CheckStage(Number: Integer): Integer;")
        self.assertIn("else if Number <= 15 then Result := 3", stage)
        self.assertIn("Test-Case 'AC-A5 the PC check has no C15 and no C30", self.tests)

    def test_qa_n1_the_admin_signs_in_with_the_setup_password_and_m01_sends_no_invitation(
        self,
    ) -> None:
        # DEC-0041: no invitation email; S15 step 1 is to sign in at the address with the S08
        # email address and password, and M01 has no "Send my invitation again".
        copy = read_copy()
        for key in ("s15_step1", "s15_step1_no_address"):
            with self.subTest(key=key):
                self.assertIn(
                    "1. Open Slate Operations on this PC at https://%1. Sign in with",
                    copy.get(key, ""),
                )
                self.assertNotIn("invitation", copy.get(key, ""))
        finished = self.part("procedure RenderFinishedPage;")
        self.assertIn("FM2('s15_step1', AddressHost(''), Trim(OrgEmail.Text))", finished)
        for gone in ("InviteClick", "InviteDone", "'invite'", "m01_invite", "'resend-invitation'"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, self.raw)
        self.assertFalse([key for key in copy if key.startswith("m01_invite")])
        self.assertIn("SelfRecord('QA N1 S15 step 1 signs in at the address", self.selftest)

    def test_qa_n4_a_restart_continues_only_for_the_setup_version_that_asked(self) -> None:
        # DEC-0038: progress of another setup file is an unfinished run.
        entry = self.windows.split("function Get-SetupEntry {", 1)[1].split("\nfunction ", 1)[0]
        self.assertIn(
            "$sameVersion = [bool]($SetupVersion -and ([string](Get-DictValue $Progress "
            "'setup_version') -ceq $SetupVersion))",
            entry,
        )
        self.assertLess(
            entry.index("-not $sameVersion"), entry.index("'feature_restart') { return")
        )
        self.assertIn("-SetupVersion $saverVersion", self.helper)
        self.assertIn("$record['setup_version'] = $SetupVersion", self.windows)
        removal = (PS_TESTS / "Removal.Tests.ps1").read_text(encoding="ascii")
        self.assertIn(
            "Test-Case 'QA N4 a restart continues only when the same setup version", removal
        )


class ReviewFixTest(unittest.TestCase):
    """Review fix round R-1 to R-8 (TASK-0097): Security Engineer S97-3, S97-4, S97-8, S97-9;
    Software Architect N-1, N-5, N-6, N-8; Product Designer copy rulings. Behavior: the Pester
    cases in Removal.Tests.ps1 and the [Code] self-test."""

    def setUp(self) -> None:
        self.raw = pascal_code()
        self.selftest = SELFTEST.read_text(encoding="ascii")
        self.helper = (SCRIPTS / "setup-helper.ps1").read_text(encoding="ascii")
        self.windows = (SCRIPTS / "lib/Windows.ps1").read_text(encoding="ascii")
        self.uninstall = (SCRIPTS / "lib/Uninstall.ps1").read_text(encoding="ascii")
        self.removal = (PS_TESTS / "Removal.Tests.ps1").read_text(encoding="ascii")
        self.copy = read_copy()

    def part(self, head: str) -> str:
        self.assertIn(head, self.raw)
        return routine(self.raw, head)

    def test_r1_a_finished_install_or_an_unreadable_program_is_never_removed(self) -> None:
        entry = self.windows.split("function Get-SetupEntry {", 1)[1].split("\nfunction ", 1)[0]
        self.assertIn(
            "if ($ProgramUnreadable) { return @{ screen = 'S01'; next = '';"
            " program_unreadable = $true } }",
            entry,
        )
        self.assertLess(entry.index("$ProgramUnreadable) { return"), entry.index("$stage = ''"))
        self.assertLess(
            entry.index("if ($stage -eq 'key_saved') { return @{ screen = 'S01'; next = '' } }"),
            entry.rindex("cleanup = $true"),
        )
        self.assertIn("-ProgramUnreadable:$unreadable", self.helper)
        self.assertIn(
            "ProgramUnreadable := Pos('\"program_unreadable\":true', Text) > 0;", self.raw
        )
        self.assertIn("CM('s01_program_unreadable')", self.raw)
        self.assertIn("@('key_saved', $true, '', 'S01  '),", self.removal)
        self.assertIn(
            "Test-Case 'R-1 a program record that exists but cannot be read", self.removal
        )

    def test_r2_s08_takes_the_password_rule_of_the_install_job(self) -> None:
        self.assertEqual(
            self.copy.get("s08_password_help"),
            "Use 12 to 72 characters. You sign in with this password.",
        )
        self.assertEqual(self.copy.get("s08_err_password"), "Use 12 to 72 characters.")
        self.assertEqual(
            self.copy.get("s08_err_password_long"),
            "This password is too long. Use a shorter password.",
        )
        install = self.part("procedure PollInstall;")
        self.assertIn(
            "else if Code = 'invalid_input' then InstallFail(6, CM('s12_invalid_input'))", install
        )
        self.assertIn(
            "SelfRecord('R-2 S08 password rule (12 characters to 72 UTF-8 bytes)'", self.selftest
        )

    def test_r3_the_designer_strings(self) -> None:
        expected = {
            "s08_email_help": "You sign in to Slate Operations with this address.",
            "s08_slug": "Address name",
            "s08_err_label_in_use": "Another device on this network already uses %1. "
            "Choose another address name.",
            "s12_step_limit": "This step took longer than setup allows.",
            "m02_test_sent_admin": "Slate Operations sent a test email to the administrator's "
            "address. Check that inbox and its Spam folder.",
            "m02_sending": "Sending a test email to the administrator's address.",
            "remove_limit": "A step took too long, so setup stopped the removal. The next time you "
            "start setup, it removes the rest.",
            "s15_step2": "2. Set up email, so Slate Operations can send invitations and password "
            "resets. Open Slate Operations settings in the Start menu and select Set up email.",
            "step_install_admin": "Creating your administrator account for %2.",
            "m01_email": "Set up email",
            "m02_title": "Set up email",
            "m02_done": "Slate Operations sends email from %1 now.",
            "step_smtp_test_stage": "Saving the email settings for Slate Operations.",
        }
        for key, value in expected.items():
            with self.subTest(key=key):
                self.assertEqual(self.copy.get(key), value)
        self.assertTrue(
            self.copy["s01_text"].endswith("%n%nHave ready: a USB drive for backups (recommended).")
        )
        self.assertTrue(
            self.copy["remove_stages"].startswith("Stop the install step that is running|")
        )
        finished = self.part("procedure RenderFinishedPage;")
        self.assertLess(
            finished.index("PlaceFinishedText(0, Step1, Y);"), finished.index("S15Open.SetBounds(")
        )
        self.assertLess(
            finished.index("S15Open.SetBounds("),
            finished.index("PlaceFinishedText(1, CM('s15_step2'), Y);"),
        )
        self.assertIn("PlaceFinishedText(1, '', Y)", finished)
        self.assertIn(
            "else if MailSaved then MailStatus.Caption := CM('m02_test_sent_admin')", self.raw
        )
        self.assertIn("AddText(CM('s07_av_blocked'), False)", self.raw)
        for record in (
            "'R-3 S15 Open under step 1, then step 2'",
            "'R-3 M02 with no sent_to names the administrator'",
            "'R-3 the stopped removal lines fit the form'",
            "'R-3 S07 security program line'",
        ):
            with self.subTest(record=record):
                self.assertIn(record, self.selftest)

    def test_r4_cancel_during_s05_waits_for_its_step(self) -> None:
        start = self.part("procedure StartCloseFlow(Flow, After: String);\nbegin")
        self.assertIn("if PrepState = 'working' then", start)
        self.assertLess(
            start.index("if PrepState = 'working' then"), start.index("CloseStep(1, 'job'")
        )
        self.assertIn("CloseOut := PrepOut;", start)
        self.assertIn("CloseLimitMs := DATA_LIMIT_MS - Elapsed(PrepStartedAt)", start)
        poll = self.part("procedure PollCloseFlow;\nvar")
        self.assertRegex(
            poll,
            r"if ClosePhase = 'prep' then\s+begin\s+PrepState := 'done';\s+CloseStep\(1, 'job'",
        )

    def test_r5_a_failed_data_step_keeps_the_records(self) -> None:
        poll = self.part("procedure PollCloseFlow;\nvar")
        self.assertRegex(
            poll,
            r"if \(Code <> 'removed'\) and \(Code <> 'returned'\) and \(Code <> 'nothing'\) then"
            r"\s+begin\s+EndCloseFlow\('data'\);",
        )
        self.assertLess(poll.index("EndCloseFlow('data');"), poll.index("'remove-windows'"))
        kept = self.uninstall.split("function Remove-SetupData {", 1)[1].split("\nfunction ", 1)[0]
        self.assertIn("} catch {", kept)
        self.assertEqual(kept.count("-Code 'keep_failed'"), 3)
        self.assertIn(
            "Test-Case 'R-5 any failure in the kept branch returns keep_failed", self.removal
        )

    def test_r6_the_removal_window_shows_before_its_work(self) -> None:
        run = self.part("function RunRemoval(Why: String): Boolean;\nbegin")
        self.assertIn("RemoveStartPending := True;", run)
        self.assertLess(
            run.index("RemoveStartPending := True;"), run.index("RemoveForm.ShowModal;")
        )
        self.assertNotIn("StartCloseFlow(", run)
        tick = self.part("procedure TimerTick(H, Msg, Id, Tick: Longword);")
        self.assertRegex(
            tick,
            r"if RemoveStartPending then\s+begin\s+RemoveStartPending := False;\s+"
            r"StartCloseFlow\('remove', RemoveWhy\);",
        )

    def test_r7_entra_id_accounts_count_in_the_distribution_check(self) -> None:
        names = self.uninstall.split("function Get-WslDistroNames {", 1)[1].split("\nfunction ", 1)[
            0
        ]
        self.assertEqual(names.count("Test-UserSid $sid"), 2)
        self.assertIn("'^S-1-(5-21|12-1)(-[0-9]+)+$'", self.uninstall)
        self.assertIn(
            "Test-Case 'R-7 the distribution check reads local and Microsoft Entra ID", self.removal
        )

    def test_r8_no_invitation_resend_and_no_unused_email_keys(self) -> None:
        exec_lib = (SCRIPTS / "lib/Exec.ps1").read_text(encoding="ascii")
        jobs = exec_lib.split("EngineJobs  = @(", 1)[1].split(")", 1)[0]
        self.assertNotIn("resend-invitation", jobs)
        for key in ("step_resend_invitation_resend", "s09_waiting", "s09_sending"):
            with self.subTest(key=key):
                self.assertNotIn(key, self.copy)

    def test_r9_the_service_profile_goes_after_its_processes_or_its_record_stays(self) -> None:
        # R-9 (exec-path CI on 7ff565a1): the profile was loaded, so remove-windows skipped it.
        def body(name: str) -> str:
            self.assertIn(f"function {name} {{", self.uninstall)
            return self.uninstall.split(f"function {name} {{", 1)[1].split("\nfunction ", 1)[0]

        self.assertNotIn("if ($userProfile -and -not $userProfile.Loaded)", self.uninstall)
        stop = body("Stop-AccountProcesses")
        self.assertIn("if ($Sid -notmatch '^S-1-5-21(-[0-9]+)+$') { return 0 }", stop)
        self.assertIn("GetCurrent().User.Value) { return 0 }", stop)
        profile = body("Remove-ServiceProfile")
        self.assertIn("if (-not $userProfile.Loaded) {", profile)
        self.assertLess(
            profile.index("$null = & $StopProcesses $Sid"),
            profile.index("& $DeleteProfile $userProfile"),
        )
        self.assertIn("if ([DateTime]::UtcNow -ge $deadline) {", profile)
        self.assertLess(
            profile.index("[regex]::Escape($AccountName)"), profile.index("& $StopProcesses $Sid")
        )
        service = (SCRIPTS / "lib/Service.ps1").read_text(encoding="ascii")
        self.assertLess(
            service.index("$null = Remove-ServiceProfile -Sid $stale"),
            service.index("$record.Remove('account_sid')"),
        )
        parts = body("Remove-WindowsParts")
        self.assertLess(
            parts.index("$outcome.profile_left = -not (& $RemoveProfile $sid)"),
            parts.index("Remove-LocalUser -SID $sid"),
        )
        self.assertIn(
            "Write-JsonFile -Path $keepRecord -Value ([ordered]@{ account_sid = $sid })", parts
        )
        self.assertIn("$left.Add('profile')", body("Get-UninstallLeftovers"))
        tests = (PS_TESTS / "Uninstall.Tests.ps1").read_text(encoding="ascii")
        for case in (
            "Test-Case 'R-9 the service profile goes after the account processes end;",
            "Test-Case 'R-9 when no startup task can be registered, the record keeps only",
        ):
            with self.subTest(case=case):
                self.assertIn(case, tests)

    def test_r10_a_profile_still_loaded_goes_to_one_startup_task(self) -> None:
        # R-10 (exec-path CI on e4b73ba6): the profile stayed loaded after the kill and the wait.
        def body(name: str) -> str:
            self.assertIn(f"function {name} {{", self.uninstall)
            return self.uninstall.split(f"function {name} {{", 1)[1].split("\nfunction ", 1)[0]

        profile = body("Remove-ServiceProfile")
        self.assertIn("[int]$LimitSeconds = 45,", profile)
        self.assertIn("(& $Facts $Sid)", profile)
        self.assertIn("GetSubKeyNames()) -contains $Sid", body("Get-ServiceProfileFacts"))
        finish = body("Get-ProfileFinishScript")
        self.assertLess(
            finish.index("if ($Sid -cnotmatch $SlateOpsKept.SidPattern) { throw"),
            finish.index("$lines = @("),
        )
        self.assertLess(
            finish.index("'if ($userProfile -and $userProfile.Loaded) { return }'"),
            finish.index("Unregister-ScheduledTask -TaskPath"),
        )
        register = body("Register-ProfileFinishTask")
        self.assertIn(
            "New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount"
            " -RunLevel Highest",
            register,
        )
        self.assertIn("-Trigger (New-ScheduledTaskTrigger -AtStartup)", register)
        self.assertIn("-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries", register)
        names = body("Get-UninstallNames")
        self.assertIn("FinishTaskPath = '\\'", names)
        self.assertIn("FinishTaskPrefix = 'SlateOpsFinishRemoval-'", names)
        parts = body("Remove-WindowsParts")
        self.assertLess(
            parts.index("Invoke-UninstallPart 'tasks'"), parts.index("& $RemoveProfile $sid")
        )
        self.assertLess(
            parts.index("& $RemoveProfile $sid"), parts.index("(& $RegisterFinish $sid)")
        )
        self.assertLess(
            parts.index("(& $RegisterFinish $sid)"), parts.index("Remove-LocalUser -SID $sid")
        )
        self.assertIn("-Code 'removed_at_restart'", parts)
        self.assertIn("(& $RemoveProfile $old 5)", parts)
        maintenance = (INSTALLER / "wizard/Maintenance.iss").read_text(encoding="ascii")
        self.assertIn(
            "(RemoveFeaturesCode <> 'removed') and"
            " (RemoveWindowsCode <> 'removed_at_restart') then",
            maintenance,
        )
        self.assertIn(
            "if RemoveWindowsCode = 'removed_at_restart' then"
            " AddText(CM('remove_account_restart'), False);",
            maintenance,
        )
        uninstall_iss = (INSTALLER / "wizard/Uninstall.iss").read_text(encoding="ascii")
        self.assertIn(
            "UAccountRestart := JsonValue(Text, 'code') = 'removed_at_restart';", uninstall_iss
        )
        self.assertIn("remove_account_restart", self.copy)
        self.assertIn("'R-10 the account line at the next restart fits the form'", self.selftest)
        exec_path = (PS_TESTS / "exec-path.ps1").read_text(encoding="ascii")
        self.assertIn("Write-AccountProbe -Sid $sid -When ('after {0}' -f $action)", exec_path)
        self.assertIn("Write-ProfileEvents -Sid $sid", exec_path)
        self.assertIn("$taskProblem = Get-FinishTaskProblem -Sid $sid -Name $finishName", exec_path)
        tests = (PS_TESTS / "Uninstall.Tests.ps1").read_text(encoding="ascii")
        for case in (
            "Test-Case 'R-10 the removal waits for the hive to unload",
            "Test-Case 'R-10 the startup task script deletes the profile only when it is not",
            "Test-Case 'R-10 the order is tasks, then the profile, then the account;",
            "Test-Case 'R-10 the startup task registers as SYSTEM at startup",
        ):
            with self.subTest(case=case):
                self.assertIn(case, tests)


class OwnerRc28Test(unittest.TestCase):
    """The owner's rc.28 list (TASK-0097, W14 round 3): AC-O1, AC-O2, AC-O5, AC-O7, AC-O8, AC-O9
    and the S12 copy. Behavior: the Pester cases named here and the [Code] self-test."""

    def setUp(self) -> None:
        self.raw = pascal_code()
        self.selftest = SELFTEST.read_text(encoding="ascii")
        self.copy = read_copy()

    def script(self, name: str) -> str:
        return (SCRIPTS / name).read_text(encoding="ascii")

    def ps_tests(self, name: str) -> str:
        return (PS_TESTS / name).read_text(encoding="ascii")

    def test_ac_o1_a_waiting_restart_is_recorded_and_never_blocks(self) -> None:
        checks = self.script("lib/Checks.ps1")
        self.assertIn("New-CheckResult 'C08' 'log' 'pending' @{ values_set = $set }", checks)
        self.assertNotIn("New-CheckResult 'C08' 'fix'", checks)
        self.assertNotIn("Id = 'C08'", self.raw)
        for key in ("c08_btn", "c08_pending", "s02_restart_confirm"):
            with self.subTest(key=key):
                self.assertNotIn(key, self.copy)
        self.assertIn("CheckRestart(Index)", self.raw)
        self.assertIn(
            "Test-Case 'AC-O1 C08 only records a waiting restart", self.ps_tests("Checks.Tests.ps1")
        )

    def test_ac_o2_setup_accepts_its_own_state_folder_after_a_removal(self) -> None:
        windows = self.script("lib/Windows.ps1")
        for code in ("unsafe_link", "unsafe_owner", "unsafe_access"):
            with self.subTest(code=code):
                self.assertIn(f"code = '{code}'", windows)
                self.assertIn(f"s01_state_{code}", self.copy)
        self.assertIn("function Get-StaleServiceSid {", windows)
        self.assertIn("$identity.Translate([System.Security.Principal.NTAccount])", windows)
        self.assertIn(
            "if (-not $serviceSid) { $step = Repair-StaleStateFolder -Layout $layout -Step $step }",
            self.script("setup-helper.ps1"),
        )
        self.assertIn("function Clear-TreeAccount {", self.script("lib/Common.ps1"))
        self.assertIn(
            "$changed = Clear-TreeAccount -Tree $Layout.StateTree -Sid $sid",
            self.script("lib/Uninstall.ps1"),
        )
        self.assertIn("StateUnsafe := Pos('unsafe', StateCheckCode) = 1;", self.raw)
        self.assertIn("Result := CM('s01_state_' + StateCheckCode)", self.raw)
        self.assertIn(
            "Test-Case 'AC-O2 a state folder that a removal left",
            self.ps_tests("Folders.Tests.ps1"),
        )
        self.assertIn(
            "Test-Case 'AC-O2 the removal leaves no entry", self.ps_tests("Uninstall.Tests.ps1")
        )

    def test_ac_o5_the_verdict_hides_its_caret_after_every_focus(self) -> None:
        self.assertIn("function VerdictProc(", self.raw)
        verdict = routine(self.raw, "function VerdictProc(")
        self.assertLess(
            verdict.index("DefSubclassProc(Wnd, Msg, W, L)"), verdict.index("HideCaret(Wnd)")
        )
        self.assertIn("RemoveWindowSubclass(Wnd, VerdictSubclass, 1)", verdict)
        self.assertIn("KeepCaretHidden(Result);", routine(self.raw, "function AddVerdict("))
        self.assertIn("'AC-O5 a verdict that gets the focus shows no text cursor'", self.selftest)

    def test_ac_o7_report_and_responder_take_an_empty_collection(self) -> None:
        self.assertIn(
            "[AllowEmptyCollection()][System.Collections.Generic.List[string]]$LeftOut",
            self.script("lib/Report.ps1"),
        )
        self.assertEqual(
            self.script("lib/Mdns.ps1").count("[AllowEmptyCollection()][byte[]]$Data"), 4
        )
        self.assertIn(
            "Test-Case 'AC-O7 Save report works when nothing is left out",
            self.ps_tests("Wizard.Tests.ps1"),
        )
        self.assertIn("Test-Case 'AC-O7 an empty UDP packet", self.ps_tests("Address.Tests.ps1"))

    def test_ac_o8_the_removal_window_closes_only_after_the_removal(self) -> None:
        self.assertIn("Result := (ClosePhase <> '') or RemoveStartPending;", self.raw)
        self.assertIn("CanClose := not RemovalRunning;", self.raw)
        self.assertIn(
            "Result.OnCloseQuery := @RemoveCloseQuery;",
            routine(self.raw, "function BuildRemoveForm("),
        )
        self.assertIn(
            "RemoveClose.Enabled := not RemovalRunning;",
            routine(self.raw, "procedure RenderRemove;"),
        )
        run = routine(self.raw, "function RunRemoval(Why: String): Boolean;\nbegin")
        self.assertLess(
            run.index("RemoveStartPending := True;"), run.index("BuildRemoveForm(Why);")
        )
        self.assertIn(
            "'AC-O8 the removal window closes only after the removal ended'", self.selftest
        )

    def test_ac_o9_a_refused_job_shows_and_logs_what_it_saw(self) -> None:
        self.assertIn("function Get-EngineRefusalDetail {", self.script("lib/Exec.ps1"))
        helper = self.script("setup-helper.ps1")
        self.assertIn("'WARN' ('refused {0}: {1}'", helper)
        self.assertIn("$values.detail = $detail", helper)
        self.assertIn("FailDetail := JsonValue(JobRaw, 'detail');", self.raw)
        self.assertIn("FailDetailLink.OnLinkClick := @ShowFailDetail;", self.raw)
        self.assertIn("InfoForm(CM('s13_details_title'), FailDetail);", self.raw)
        self.assertIn(
            "'AC-O9 a refused prepare shows its detail under Details on S13'", self.selftest
        )
        self.assertIn(
            "Test-Case 'AC-O9 a refused prepare gives its detail", self.ps_tests("Exec.Tests.ps1")
        )

    def test_s12_copy_has_no_second_time_line_and_no_drive_before_a_stop(self) -> None:
        # Spec 6.3 (7334a07c): the subtitle keeps "This can take up to 30 minutes."; the time
        # text of S12 no longer repeats it (the wait passes no limit sentence).
        self.assertEqual(self.copy["s12_subtitle"], "This can take up to 30 minutes.")
        self.assertNotIn("wait_up_to_30", self.raw)
        # Each line whose value is a drive letter ("D:") names it as "the D: drive", so no
        # sentence ends in "D:." (owner, rc.28).
        drives = {
            "c07_too_small": "%2",
            "s10_not_writable": "%1",
            "s12_backup_failed": "%1",
            "step_bg_import": "%1",
            "step_backup_check": "%1",
            "step_set_backup_target_unmount": "%1",
            "step_set_backup_target_mount": "%2",
            "step_set_backup_target_repository": "%2",
            "step_new_recovery_key_mount": "%1",
            "m03_mount_line": "%1",
            "m03_key_line": "%1",
            "step_repair_backup": "%2",
            "step_upd_copy": "%2",
        }
        for key, value in drives.items():
            with self.subTest(key=key):
                self.assertRegex(self.copy[key], rf"the {value} (backup )?drive")
                self.assertNotIn(f"{value}.", self.copy[key])


class StripAndBarTest(unittest.TestCase):
    """Owner items 3 and 4 (TASK-0097): spec 7334a07c 6.2 (step strip) and 6.3 (progress bar
    with the time). Behavior: the self-test checks named "TASK-0097 ..." on Windows CI."""

    def setUp(self) -> None:
        self.raw = pascal_code()
        self.selftest = SELFTEST.read_text(encoding="ascii")
        self.copy = read_copy()

    def test_6_3_copy_keys_hold_the_spec_strings(self) -> None:
        expected = {
            "stage_1": "1 Check this PC",
            "stage_2": "2 Your details",
            "stage_3": "3 Install",
            "stage_4": "4 Done",
            "strip_name_1": "Check this PC",
            "strip_name_2": "Your details",
            "strip_name_3": "Install",
            "strip_name_4": "Done",
            "strip_done_mark": "\u2713",
            "wait_so_far": "%1 so far",
            "wait_join": "%1 \u00b7 %2",
            "wait_left": "About %1 minutes left",
            "wait_left_1": "About 1 minute left",
            "wait_longer": "This step takes longer than usual",
            "wait_usually": "Usually about %1 minutes",
            "wait_usually_1": "Usually about 1 minute",
            "wait_finished": "Finished in %1",
            "s12_subtitle": "This can take up to 30 minutes.",
            "step_install_backup": "Making the first backup on the %3 drive.",
        }
        for key, value in expected.items():
            with self.subTest(key=key):
                self.assertEqual(self.copy.get(key), value)
        self.assertIn("Copy the server part to the %1 drive", self.copy["bg_stages"].split("|"))
        for retired in (
            "stage_sep",
            "wait_time",
            "wait_time_limit",
            "wait_about_1",
            "wait_about_2",
        ):
            with self.subTest(retired=retired):
                self.assertNotIn(retired, self.copy)
                self.assertNotIn(f"'{retired}'", self.raw)

    def test_6_3_no_drive_letter_before_a_stop_and_no_marquee(self) -> None:
        for key, value in self.copy.items():
            with self.subTest(key=key):
                self.assertNotRegex(value, r"[A-Z]:\.")
        self.assertNotIn("npbstMarquee", self.raw)
        self.assertNotIn("npbstMarquee", self.selftest)

    def test_6_2_the_strip_is_static_text_on_every_setup_page(self) -> None:
        self.assertIn("function StripAt(", self.raw)
        strip = routine(self.raw, "function StripAt(")
        self.assertIn("function StripStep(Index: Integer): Integer;", self.raw)
        for fact in (
            "Cap.TabStop := False;",
            "Mark.Font.Name := 'Segoe UI Symbol';",
            "Line.Color := clHighlight;",
            "Cap.Font.Color := clGrayText;",
            "Result := Top + TextH + ScaleY(16);",
        ):
            with self.subTest(fact=fact):
                self.assertIn(fact, strip)
        step = routine(self.raw, "function StripStep(Index: Integer): Integer;")
        self.assertIn("if EntryNext = 'S14' then Result := 4 else Result := 1;", step)
        for page in (
            "P_CHECK",
            "P_RESTART",
            "P_BACK",
            "P_DATA",
            "P_BACKUP",
            "P_READY",
            "P_INSTALL",
            "P_KEY",
        ):
            with self.subTest(page=page):
                self.assertIn(f"AddStageLine(StripStep({page}));", self.raw)
        self.assertIn("OrgTop := StageLineAt(Surface, 0, StripStep(P_ORG));", self.raw)
        self.assertIn("MailTop := 0;", self.raw)
        self.assertIn("StripAt(WizardForm.LicensePage, WizardForm.LicenseMemo.Left", self.raw)
        finished = routine(self.raw, "procedure RenderFinishedPage;")
        self.assertIn(
            "StripAt(WizardForm.FinishedPage, WizardForm.FinishedHeadingLabel.Left", finished
        )
        self.assertIn("the strip leaves S15 (spec 6.2)", finished)
        self.assertNotIn("CM('stage_sep')", self.raw)

    def test_6_3_one_bar_per_wait_that_never_moves_back(self) -> None:
        self.assertIn("function BarPosition(", self.raw)
        position = routine(self.raw, "function BarPosition(")
        self.assertIn("if Fill > 900 then", position)
        self.assertIn("if Result > 999 then", position)
        refresh = routine(self.raw, "procedure BarRefresh;")
        self.assertIn("if Position > BarHigh then", refresh)
        self.assertIn("WaitBar.Position := BarHigh;", refresh)
        progress = routine(self.raw, "procedure AddProgress(")
        for fact in (
            "WaitBar := TNewProgressBar.Create(WizardForm);",
            "WaitBar.Max := 1000;",
            "WaitBar.Style := npbstNormal;",
            "if BarW >= Cur.Width div 2 then",
            "WaitTime.Caption := FM1('wait_finished', BarElapsed)",
        ):
            with self.subTest(fact=fact):
                self.assertIn(fact, progress)
        self.assertIn("BarRefresh;", routine(self.raw, "procedure RefreshWaitLabels;"))
        line = routine(self.raw, "procedure LineBarShow(")
        self.assertIn(
            "B.Bar.SetBounds(B.BaseLeft, Lbl.Top + ScaleY(3), ScaleX(96), ScaleY(8));", line
        )
        self.assertIn("Lbl.Left := B.BaseLeft + ScaleX(104);", line)
        self.assertIn("if B.Shifted and (Lbl.Left <> B.BaseLeft + ScaleX(104)) then", line)
        self.assertIn("UninstallProgressForm.ProgressBar.Visible := False;", self.raw)
        self.assertIn(
            "Result := CreateCustomForm(ScaleX(480), ScaleY(360), False, False);", self.raw
        )
        weights = routine(self.raw, "function BarWeights(Kind: String): String;\nvar")
        for fact in (
            "Result := Result + '|60|15|10|120|30|15|180|120';",
            "else if Kind = 'prep' then Result := '45|75|5|0|0'",
            "else if Kind = 'remove' then Result := '5|15|60|60|40'",
            "else if Kind = 'm03' then Result := '5|10|30|30'",
        ):
            with self.subTest(fact=fact):
                self.assertIn(fact, weights)
        for record in (
            "'TASK-0097 strip state per page'",
            "'TASK-0097 fit with the strip and the bar'",
            "'TASK-0097 the bar never moves back'",
            "'TASK-0097 time left never goes up'",
            "'TASK-0097 a tick changes only the time and the bar'",
            "'TASK-0097 no drive letter before a full stop'",
            "'TASK-0097 a compact bar follows its label and gives it back'",
        ):
            with self.subTest(record=record):
                self.assertIn(record, self.selftest)
