"""Static contract tests for the trust page that Caddy serves on port 80 (plan W6b)."""

from __future__ import annotations

import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRUST_PAGE = ROOT / "infra" / "caddy" / "trust" / "index.html"

# The two download paths that W6a serves next to the page (plan 6.3).
DOWNLOAD_PATHS = {"/trust/slateops-ca.crt", "/trust/slateops.mobileconfig"}
URL_ATTRIBUTES = {"href", "src", "srcset", "action", "formaction", "poster", "data", "background"}


class _Urls(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []
        self.tags: set[str] = set()
        self.script_sources: list[str] = []
        self._in_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.add(tag)
        self._in_script = tag == "script"
        for name, value in attrs:
            if name in URL_ATTRIBUTES and value is not None:
                self.urls.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_script = False

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self.script_sources.append(data)


def _page_text() -> str:
    return TRUST_PAGE.read_text(encoding="utf-8") if TRUST_PAGE.is_file() else ""


class TrustPageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = _page_text()
        self.parsed = _Urls()
        self.parsed.feed(self.text)
        self.script = "\n".join(self.parsed.script_sources)

    def test_page_loads_nothing_from_another_origin_and_links_only_the_trust_files(self) -> None:
        # W6b-2: no request to another host. W6a-1: port 80 serves only the trust paths.
        self.assertEqual(
            DOWNLOAD_PATHS, {url for url in self.parsed.urls if not url.startswith("#")}
        )
        self.assertEqual(
            set(), {"link", "base", "iframe", "object", "embed", "img"} & self.parsed.tags
        )
        self.assertIsNone(
            re.search(r"https?://[A-Za-z0-9\[]", self.text), "a literal host in the page"
        )
        self.assertNotIn("url(", self.text)
        self.assertNotIn("@import", self.text)
        for api in ("XMLHttpRequest", "sendBeacon", "EventSource", "WebSocket", "import("):
            self.assertNotIn(api, self.script)

    def test_script_writes_no_markup(self) -> None:
        # The script sets only text and attributes, so no string becomes markup.
        for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
            self.assertNotIn(sink, self.script)

    def test_every_fetch_omits_credentials(self) -> None:
        # W6a-7 and W6b-3: the status check never sends a cookie.
        fetches = re.findall(r"fetch\(", self.script)
        self.assertEqual(1, len(fetches))
        self.assertEqual(["omit"], re.findall(r"credentials:\s*['\"](\w+)['\"]", self.script))
        self.assertIn('"/trust/ok"', self.script)

    def test_only_template_action_reads_the_engine_fingerprint_file(self) -> None:
        # W6b-1 with the W6a contract: Caddy `templates` renders the page, so every `{{`
        # is an action, and the only actions read `slateops-ca.sha256` as data, escaped.
        # `include` would run the engine's file as a template; `readFile` does not.
        actions = re.findall(r"\{\{(.*?)\}\}", self.text, flags=re.DOTALL)
        self.assertEqual(
            [
                'if fileExists "slateops-ca.sha256"',
                'readFile "slateops-ca.sha256" | trim | html',
                "end",
            ],
            [action.strip() for action in actions],
        )

    def test_ac_b9_the_code_shows_openly_before_the_steps_until_the_device_trusts_it(
        self,
    ) -> None:
        # TASK-0097 AC-B9: the owner never saw the code in the closed "Check the code"
        # section at the bottom. Until the device trusts Slate Operations, the code stands
        # under the status line, before the steps; with "Yes" the short page stays.
        text = self.text
        code = text.index('id="code"')
        self.assertLess(text.index('id="status"'), code)
        self.assertLess(code, text.index('id="steps-area"'))
        block = text[code : text.index("</section>", code)]
        self.assertIn("Check that this code matches the code on the server PC", block)
        self.assertIn('{{readFile "slateops-ca.sha256" | trim | html}}', block)
        self.assertNotIn("<details", text)
        self.assertRegex(
            self.script,
            r'code\.hidden = state === "yes"|getElementById\("code"\)\.hidden = state === "yes"',
        )


if __name__ == "__main__":
    unittest.main()
