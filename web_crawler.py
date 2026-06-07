"""
Playwright-based web crawler for DOM extraction.

Crawls an authenticated web application, extracts all interactive elements
from every reachable page, and returns structured PageInfo objects ready for
feature file and page-object generation.
"""

import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from urllib.parse import urldefrag, urljoin, urlparse
from utils.logger import AppLogger

logger = AppLogger.get_logger("web_crawler")

# ------------------------------------------------------------------ #
#  Data models                                                         #
# ------------------------------------------------------------------ #

@dataclass
class ElementInfo:
    tag: str
    element_type: str          # input | button | link | select | textarea | checkbox | radio
    text: str = ""
    placeholder: str = ""
    el_id: str = ""
    el_name: str = ""
    el_input_type: str = ""    # text | password | email | submit | …
    css_classes: str = ""
    aria_label: str = ""
    data_attrs: Dict[str, str] = field(default_factory=dict)
    href: str = ""
    options: List[str] = field(default_factory=list)
    is_required: bool = False

    # Generated locators — keyed by strategy name
    locators: Dict[str, str] = field(default_factory=dict)
    best_locator: str = ""         # the locator value
    best_locator_strategy: str = "" # id | name | css | xpath | aria
    java_var_name: str = ""        # camelCase field name for Page Object
    python_var_name: str = ""      # snake_case


@dataclass
class PageInfo:
    url: str
    title: str
    page_name: str                 # derived from URL path
    elements: List[ElementInfo] = field(default_factory=list)
    forms: List[Dict] = field(default_factory=list)
    nav_links: List[Dict] = field(default_factory=list)
    all_links: List[str] = field(default_factory=list)

    def to_summary_text(self) -> str:
        """Compact text for LLM context — avoids token bloat."""
        lines = [
            f"PAGE: {self.page_name}  ({self.url})",
            f"TITLE: {self.title}",
            "ELEMENTS:",
        ]
        for el in self.elements:
            label = el.text or el.placeholder or el.aria_label or el.el_name or el.el_id or "?"
            loc = f"{el.best_locator_strategy}={el.best_locator}" if el.best_locator else "no-locator"
            lines.append(f"  [{el.element_type.upper()}] '{label[:60]}' | {loc}")
        if self.forms:
            lines.append("FORMS:")
            for f in self.forms:
                lines.append(f"  form#{f.get('id','?')} fields: {f.get('field_summary','')}")
        return "\n".join(lines)


# ------------------------------------------------------------------ #
#  Locator generation                                                  #
# ------------------------------------------------------------------ #

def _best_locator(el: dict) -> tuple[str, str]:
    """
    Priority: data-testid > data-cy > id > name > aria-label > css > xpath
    Returns (strategy, value).
    """
    data = el.get("dataAttrs", {})
    for attr in ("data-testid", "data-cy", "data-test", "data-automation-id", "data-qa"):
        if data.get(attr):
            return ("css", f"[{attr}='{data[attr]}']")

    if el.get("id"):
        return ("id", el["id"])

    if el.get("name"):
        return ("name", el["name"])

    if el.get("ariaLabel"):
        return ("css", f"[aria-label='{el['ariaLabel']}']")

    tag = el.get("tag", "div")
    text = (el.get("text") or "").strip()
    if tag == "button" and text:
        return ("xpath", f"//button[normalize-space()='{text[:50]}']")
    if tag == "a" and text:
        return ("link_text", text[:50])

    # CSS fallback using type + classes
    el_type = el.get("type", "")
    classes = (el.get("classes") or "").split()
    stable_class = next((c for c in classes if not re.match(r".*\d{3,}", c)), "")
    if stable_class:
        return ("css", f"{tag}.{stable_class}")
    if el_type:
        return ("css", f"{tag}[type='{el_type}']")

    return ("xpath", f"//{tag}")


def _to_camel(text: str) -> str:
    words = re.sub(r"[^a-zA-Z0-9 ]", " ", text).split()
    if not words:
        return "element"
    return words[0].lower() + "".join(w.capitalize() for w in words[1:])


def _to_snake(text: str) -> str:
    words = re.sub(r"[^a-zA-Z0-9 ]", " ", text).split()
    return "_".join(w.lower() for w in words) or "element"


def _classify(el: dict) -> str:
    tag = el.get("tag", "").lower()
    el_type = (el.get("type") or "").lower()
    if tag == "a":
        return "link"
    if tag == "button" or el_type in ("button", "submit", "reset"):
        return "button"
    if tag == "select":
        return "select"
    if tag == "textarea":
        return "textarea"
    if el_type == "checkbox":
        return "checkbox"
    if el_type == "radio":
        return "radio"
    if el_type == "password":
        return "password_input"
    if el_type in ("text", "email", "tel", "number", "search", "url", "date"):
        return "input"
    if tag == "input":
        return "input"
    return "element"


def _build_element_info(el: dict) -> ElementInfo:
    strategy, locator_value = _best_locator(el)
    label = el.get("text") or el.get("placeholder") or el.get("ariaLabel") or el.get("name") or el.get("id") or el.get("tag", "el")

    all_locators = {}
    if el.get("id"):
        all_locators["id"] = el["id"]
    if el.get("name"):
        all_locators["name"] = el["name"]
    strategy2, val2 = _best_locator(el)
    if strategy2 not in ("id", "name"):
        all_locators[strategy2] = val2

    return ElementInfo(
        tag=el.get("tag", ""),
        element_type=_classify(el),
        text=(el.get("text") or "").strip()[:100],
        placeholder=(el.get("placeholder") or "").strip(),
        el_id=el.get("id", ""),
        el_name=el.get("name", ""),
        el_input_type=(el.get("type") or "").lower(),
        css_classes=el.get("classes", ""),
        aria_label=el.get("ariaLabel", ""),
        data_attrs=el.get("dataAttrs", {}),
        href=el.get("href", ""),
        options=el.get("options", []),
        is_required=bool(el.get("required")),
        locators=all_locators,
        best_locator=locator_value,
        best_locator_strategy=strategy,
        java_var_name=_to_camel(label[:40]),
        python_var_name=_to_snake(label[:40]),
    )


# ------------------------------------------------------------------ #
#  DOM extraction script (runs inside the browser via evaluate)       #
# ------------------------------------------------------------------ #

_DOM_SCRIPT = """
() => {
    const els = [];
    const seen = new Set();

    document.querySelectorAll(
        'input:not([type=hidden]), button, a[href], select, textarea, ' +
        '[role="button"], [role="link"], [role="tab"], [role="menuitem"], ' +
        '[role="checkbox"], [role="radio"]'
    ).forEach(el => {
        const rect = el.getBoundingClientRect();
        // Skip elements with zero size (likely hidden)
        if (rect.width === 0 && rect.height === 0 && el.tagName !== 'INPUT') return;

        const key = el.tagName + '|' + (el.id || '') + '|' + (el.name || '') + '|' +
                    (el.textContent || '').trim().substring(0, 30);
        if (seen.has(key)) return;
        seen.add(key);

        const data = {
            tag: el.tagName.toLowerCase(),
            type: el.type || '',
            id: el.id || '',
            name: el.name || '',
            text: (el.textContent || '').trim().substring(0, 120),
            placeholder: el.placeholder || '',
            href: el.href || '',
            classes: el.className || '',
            ariaLabel: el.getAttribute('aria-label') || el.ariaLabel || '',
            required: el.required || false,
            dataAttrs: {},
            options: [],
            value: el.value || ''
        };

        Array.from(el.attributes).forEach(a => {
            if (a.name.startsWith('data-')) data.dataAttrs[a.name] = a.value;
        });

        if (el.tagName === 'SELECT') {
            data.options = Array.from(el.options).map(o => o.text.trim()).filter(Boolean);
        }

        els.push(data);
    });
    return els;
}
"""

_FORMS_SCRIPT = """
() => {
    return Array.from(document.forms).map(f => ({
        id: f.id || '',
        name: f.name || '',
        action: f.action || '',
        method: f.method || 'get',
        fieldCount: f.elements.length,
        fieldSummary: Array.from(f.elements)
            .filter(e => e.tagName !== 'FIELDSET')
            .map(e => (e.placeholder || e.name || e.id || e.type || e.tagName).substring(0,30))
            .join(', ')
    }));
}
"""

_LINKS_SCRIPT = """
(baseHost) => {
    return Array.from(document.querySelectorAll('a[href]'))
        .map(a => ({ href: a.href, text: (a.textContent||'').trim().substring(0,60) }))
        .filter(l => {
            try {
                const u = new URL(l.href);
                return u.hostname === baseHost && !l.href.includes('#') &&
                       !l.href.match(/\\.(pdf|jpg|png|gif|zip|docx?|xlsx?)$/i);
            } catch { return false; }
        });
}
"""


# ------------------------------------------------------------------ #
#  WebCrawler                                                          #
# ------------------------------------------------------------------ #

class WebCrawler:
    def __init__(
        self,
        base_url: str,
        username: str = "",
        password: str = "",
        max_pages: int = 15,
        headless: bool = True,
        username_selector: str = "",
        password_selector: str = "",
        submit_selector: str = "",
        login_url: str = "",
        progress_callback=None,
    ):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.max_pages = max_pages
        self.headless = headless
        self.username_selector = username_selector
        self.password_selector = password_selector
        self.submit_selector = submit_selector
        self.login_url = login_url or base_url
        self.progress_callback = progress_callback or (lambda msg: None)

        parsed = urlparse(base_url)
        self.base_host = parsed.netloc

    # ---------------------------------------------------------------- #

    def crawl(self) -> List[PageInfo]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError(
                "Playwright is not installed. Run: pip install playwright && playwright install chromium"
            )

        pages: List[PageInfo] = []
        visited: Set[str] = set()
        queue: List[str] = [self.base_url]

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self.headless)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                ignore_https_errors=True,
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/125.0 Safari/537.36"
                ),
            )
            page = context.new_page()

            # Login
            if self.username and self.password:
                self._login(page)

            # Crawl loop
            while queue and len(pages) < self.max_pages:
                url = queue.pop(0)
                clean_url, _ = urldefrag(url)
                if clean_url in visited:
                    continue
                visited.add(clean_url)

                self.progress_callback(f"Crawling: {clean_url}")
                logger.info(f"Crawling page: {clean_url}")

                try:
                    page.goto(clean_url, wait_until="networkidle", timeout=20000)
                    time.sleep(1)  # allow JS to settle

                    page_info = self._extract_page(page, clean_url)
                    pages.append(page_info)

                    for link in page_info.all_links:
                        link_clean, _ = urldefrag(link)
                        if link_clean not in visited and link_clean not in queue:
                            queue.append(link_clean)

                except Exception as exc:
                    logger.warning(f"Failed to crawl {clean_url}: {exc}")

            browser.close()

        logger.info(f"Crawl complete: {len(pages)} pages extracted")
        return pages

    # ---------------------------------------------------------------- #

    def _login(self, page):
        self.progress_callback(f"Navigating to login: {self.login_url}")
        logger.info(f"Performing login at {self.login_url}")

        try:
            page.goto(self.login_url, wait_until="networkidle", timeout=20000)
            time.sleep(1)

            # Auto-detect username field
            user_sel = self.username_selector or self._detect_username_selector(page)
            pass_sel = self.password_selector or "input[type='password']"
            submit_sel = self.submit_selector or self._detect_submit_selector(page)

            if user_sel and page.locator(user_sel).count() > 0:
                page.fill(user_sel, self.username)
                logger.info(f"Filled username field ({user_sel})")
            else:
                logger.warning("Username field not found")

            if page.locator(pass_sel).count() > 0:
                page.fill(pass_sel, self.password)
                logger.info("Filled password field")

            if submit_sel and page.locator(submit_sel).count() > 0:
                page.click(submit_sel)
                page.wait_for_load_state("networkidle", timeout=15000)
                logger.info("Login submitted — waiting for app to load")
                time.sleep(2)
            else:
                page.keyboard.press("Enter")
                page.wait_for_load_state("networkidle", timeout=15000)

            self.progress_callback("Login complete")
        except Exception as exc:
            logger.error(f"Login failed: {exc}")
            self.progress_callback(f"Login warning: {exc}")

    def _detect_username_selector(self, page) -> str:
        candidates = [
            "input[type='email']",
            "input[name='email']",
            "input[name='username']",
            "input[name='user']",
            "input[name='login']",
            "input[id='email']",
            "input[id='username']",
            "input[type='text']",
        ]
        for sel in candidates:
            if page.locator(sel).count() > 0:
                return sel
        return "input[type='text']"

    def _detect_submit_selector(self, page) -> str:
        candidates = [
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Login')",
            "button:has-text('Sign in')",
            "button:has-text('Log in')",
            "button:has-text('Submit')",
            "[data-testid*='login']",
            "[data-testid*='submit']",
        ]
        for sel in candidates:
            try:
                if page.locator(sel).count() > 0:
                    return sel
            except Exception:
                pass
        return "button[type='submit']"

    # ---------------------------------------------------------------- #

    def _extract_page(self, page, url: str) -> PageInfo:
        title = page.title() or url
        page_name = _url_to_page_name(url)

        # Extract raw DOM data
        try:
            raw_elements = page.evaluate(_DOM_SCRIPT)
        except Exception as exc:
            logger.warning(f"Element extraction failed on {url}: {exc}")
            raw_elements = []

        try:
            raw_forms = page.evaluate(_FORMS_SCRIPT)
        except Exception:
            raw_forms = []

        try:
            raw_links = page.evaluate(_LINKS_SCRIPT, self.base_host)
        except Exception:
            raw_links = []

        elements = [_build_element_info(el) for el in raw_elements]

        # Deduplicate by (element_type, best_locator)
        seen_locators: Set[str] = set()
        unique_elements: List[ElementInfo] = []
        for el in elements:
            key = f"{el.element_type}|{el.best_locator}"
            if key not in seen_locators:
                seen_locators.add(key)
                unique_elements.append(el)

        nav_links = [
            {"href": l["href"], "text": l["text"]}
            for l in raw_links
            if l.get("text") and len(l.get("text", "")) > 1
        ]
        all_links = [l["href"] for l in raw_links]

        return PageInfo(
            url=url,
            title=title,
            page_name=page_name,
            elements=unique_elements,
            forms=raw_forms,
            nav_links=nav_links,
            all_links=all_links,
        )


# ------------------------------------------------------------------ #
#  Helpers                                                             #
# ------------------------------------------------------------------ #

def _url_to_page_name(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    parts = [p for p in path.split("/") if p]
    if not parts:
        return "HomePage"
    name = parts[-1].replace("-", " ").replace("_", " ").title().replace(" ", "")
    return name + "Page" if not name.endswith("Page") else name


def summarize_crawl_for_llm(pages: List[PageInfo], max_chars: int = 14000) -> str:
    """Convert all crawled pages to a compact text block for LLM input."""
    parts = [f"APPLICATION CRAWL SUMMARY — {len(pages)} page(s) analysed\n"]
    for p in pages:
        parts.append(p.to_summary_text())
        parts.append("")
    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[... truncated for LLM context limit ...]"
    return text
