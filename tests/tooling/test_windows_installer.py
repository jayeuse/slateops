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
        prefixed = {"s12_stage", "s12_fail", "stage_", "bg_stage_"}
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
        # Security F-1: a job input file is refused by Exec for a pipe-input job (input_on_disk);
        # the smtp-test discard must go through the pipe. W14-D9: RunJobBlocking is gone, so every
        # job starts through StartJob, and a pipe-input job always passes PipeIn True.
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
        # At the slow point the task's last result decides, as on S12. W14-D9: it is the
        # job-result answer that the poll already asked for, not a blocking helper call.
        self.assertIn("if JobLogonFailed then", routine(raw, "procedure PollUpdate;\nvar"))
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
        self.assertIn("if WaitTime <> nil then", refresh)
        self.assertNotIn("RenderPage(", refresh)
        copy = read_copy()
        self.assertEqual(copy.get("wait_line"), "%1 of %2: %3 · %4")
        self.assertEqual(copy.get("wait_time"), "Time so far: %1.")
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
    "cancel_feature": "Stop setup? Virtual Machine Platform and Windows Subsystem for Linux (WSL) "
    "stay on this PC. Other programs can use them.",
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
        # The status line (6.1 L12) sits on the page area too.
        self.assertIn(
            "StatusLine.Color := Pages[P_ORG].SurfaceColor;",
            routine(self.raw, "procedure ShowStatusLine(Text: String);"),
        )
        # S08 and S09 sit on the page surface: their stage line is built there (6.1, S02 to S12).
        self.assertIn("OrgTop := StageLineAt(Surface, 0, 2);", self.raw)
        self.assertIn("MailTop := StageLineAt(Surface, 0, 2);", self.raw)
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
        self.assertLess(failure.index("CM('s12_choose_drive')"), failure.index("AddReportButton;"))

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
            "Place(OrgMoreLink, Y, not OrgMoreOpen, ScaleY(4));",
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
        self.assertIn("The only exception to the full width: S09 with Other selected", rule)
        self.assertIn('"Show" sits at the right end of the Password label\'s line', rule)
        selftest = (INSTALLER / "wizard/SelfTest.iss").read_text(encoding="ascii")
        forms = routine(selftest, "procedure SelfFormPages;")
        self.assertIn(
            "SelfRecord('W14-D3 S09 Other with every field fits above the status line', Ok,", forms
        )
        self.assertIn("MailLater.Top + MailLater.Height <= StatusBandTop - ScaleY(12)", forms)
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

    def test_ac_1_a_resume_unpacks_and_prepares_the_data_folder_before_the_background(
        self,
    ) -> None:
        # QA B1, Architect A-B1: rc.22's continue_later resumes at background step 1 with rc.22's
        # parts and Exec scripts on disk; this build's receive then finds no part of its version.
        # Every resume with the background not done prepares the data folder again (one path).
        self.assertIn("BgPrepNeeded := True;", self.raw)
        start = self.part("function InitializeSetup(")
        branch = start.split("BgResume := True;", 1)[1].split("end;", 1)[0]
        self.assertIn("BgPrepNeeded := True;", branch)
        self.assertNotRegex(branch, r"InstalledVersion|SetupVersion|Compare")
        step = self.part("procedure StartBgStep;")
        self.assertLess(step.index("if BgPrepNeeded then"), step.index("BgStepName(BgIndex)"))
        prep = self.part("procedure StartBgPrep;")
        data = self.part("procedure StartDataPrepare;")
        patterns = re.search(r"QueueExtract\('([^']+)', 'data-unpack'\)", data)
        if patterns is None:
            self.fail("StartDataPrepare queues no data-unpack")
        self.assertIn(f"QueueExtract('{patterns.group(1)}', 'resume-unpack');", prep)
        finished = self.part("procedure StepFinished(ForTag, Code: String);\nvar")
        self.assertRegex(finished, r"ForTag = 'resume-unpack' then\s+StartBgPrepData")
        helper = self.part("procedure StartBgPrepData;")
        self.assertIn(
            "StartHelper('prepare-data', RunId, BgOut, '-DataRoot ' + AddQuotes(DataRoot)"
            " + ' -UseKept')",
            helper,
        )
        self.assertIn(
            "StartHelper('prepare-data', RunId, BgOut, '-DataRoot ' + AddQuotes(DataRoot))", helper
        )
        poll = self.part("procedure PollBgPrep;")
        ready = poll.split("if Code = 'ready' then", 1)[1]
        self.assertLess(ready.index("BgPrepNeeded := False;"), ready.index("StartBgStep;"))
        self.assertIn("BgFailed := True;", poll)
        self.assertIn("DATA_LIMIT_MS", poll)
        self.assertIn("PollBgPrep", self.part("procedure PollBackground;"))
        # The helper action and the script function: this version's parts, then the receive
        # parts of other versions go (as after an update, 7bf1c939).
        helper_script = (SCRIPTS / "setup-helper.ps1").read_text(encoding="ascii")
        action = helper_script.split("'prepare-data' {", 1)[1].split("\n        }\n", 1)[0]
        self.assertIn("Invoke-PrepareData", action)
        windows = (SCRIPTS / "lib/Windows.ps1").read_text(encoding="ascii")
        self.assertIn("function Invoke-PrepareData {", windows)
        body = windows.split("function Invoke-PrepareData {", 1)[1].split("\n}\n", 1)[0]
        self.assertLess(body.index("Copy-PayloadPart"), body.index("Remove-OldPayloadParts"))
        tests = (PS_TESTS / "Wizard.Tests.ps1").read_text(encoding="ascii")
        self.assertIn("Test-Case 'AC-1 ", tests)

    def test_ac_1_a_server_part_from_another_setup_file_stops_without_try_again(self) -> None:
        # A resume after an older build imported its Linux image: import-distro answers
        # already_imported and prepare refuses the image (engine_bundle_mismatch). Try again
        # can never pass, so setup stops and names Remove everything.
        check = self.part("function CheckBackground: Boolean;")
        self.assertRegex(
            check,
            r"\(BgCode = 'engine_bundle_mismatch'\) or \(BgCode = 'image_record_missing'\)"
            r"[^;]*then\s+begin\s+FailureForm\(CM\('s07_title'\), "
            r"CM\('s07_other_version'\), False\);",
        )
        self.assertIn("s07_other_version", read_copy())

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
        # Architect N-1: Continue later and Remove everything never meet a new background job.
        # Comments removed: the gate is the first statement.
        poll = code_only(self.part("procedure PollBackground;"))
        self.assertRegex(
            poll, r"(?s)begin\s+if CloseFlowRunning then\s+Exit;\s+if PollBgPending then"
        )
        mail = code_only(self.part("procedure PollMail;"))
        self.assertRegex(
            mail,
            # code_only empties strings: the first branch is MailPhase = 'waiting'.
            r"(?s)begin\s+if MailPhase = '' then\s+begin\s+"
            r"if CloseFlowRunning then\s+Exit;\s+if BgDone then",
        )
        tick = self.part("procedure TimerTick(H, Msg, Id, Tick: Longword);")
        self.assertIn(
            "if DataStarted and not DataPrepared and (BgOut <> '') and not CloseFlowRunning then",
            tick,
        )
        # A failed save leaves setup open: the background step that the flow took over runs
        # again (the server part steps repeat safely).
        self.assertIn("RestartBackgroundStep;", self.part("procedure FailCloseFlow(Text: String);"))
        again = self.part("procedure RestartBackgroundStep;")
        self.assertIn("(BgBeganAt = 0)", again)
        self.assertIn("IsHelperStep(", again)

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
        self.assertIn("AddProgress('', S05NoRestartStages, 3, '', 0, '');", render)
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
            "later_save_failed",
            "later_restart_failed",
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

    def test_ac_8_one_line_texts_have_one_full_stop_and_fit_the_status_line(self) -> None:
        # Designer 4 and 9: "D:. · 2:10", and a status line of 18 px that a long step wraps.
        self.assertIn("function NoStop(Text: String): String;", self.raw)
        self.assertIn(
            "NoStop(Action)",
            self.part(
                "function OneLine(Number, Total: Integer; Action: String; Since: Cardinal): String;"
            ),
        )
        self.assertIn("NoStop(Action)", self.part("function BgLineText(Action: String): String;"))
        self.assertIn(
            "ShowStatusLine(BgLineText(BgAction));", self.part("procedure UpdateBgStatus;")
        )
        self.assertIn("SelfStatusLine;", routine(self.selftest, "procedure RunSelfTest;"))
        fits = routine(self.selftest, "procedure SelfStatusLine;")
        self.assertIn("SelfRecord('AC-8 every status line text fits on one line'", fits)
        listed = set(re.findall(r"SelfLineFits\('(step_[a-z_]+)'", fits))
        steps = {
            key for key in read_copy() if re.match(r"step_(bg|receive|prepare|prefetch|data)_", key)
        }
        self.assertEqual(steps - listed, set())
        for key in (
            "later_save_failed",
            "later_restart_failed",
            "remove_data",
            "remove_moving_kept",
            "s07_prep_failed",
        ):
            with self.subTest(key=key):
                self.assertIn(f"SelfLineFits('{key}'", fits)

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
