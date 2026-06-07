"""
DOM → Page Object helper.

Converts raw PageInfo objects (from WebCrawler) into structured text that
the Page Object Generator agent can turn into actual POM classes.
"""

from typing import Dict, List
from services.web_crawler import ElementInfo, PageInfo
from utils.logger import AppLogger

logger = AppLogger.get_logger("dom_extractor")


def pages_to_pom_context(pages: List[PageInfo], language: str = "Java Selenium Cucumber") -> str:
    """
    Build the LLM context block that describes every page and every element
    with its best locator — used as input to the page-object generator agent.
    """
    lang_note = {
        "Java Selenium Cucumber": "Java Selenium (@FindBy) with camelCase field names",
        "Python Behave": "Python Selenium (By.*) with snake_case attribute names",
        "C# SpecFlow": "C# Selenium ([FindsBy]) with PascalCase property names",
    }.get(language, "Java Selenium (@FindBy) with camelCase field names")

    blocks = [
        f"TARGET LANGUAGE: {language}",
        f"LOCATOR STYLE: {lang_note}",
        "=" * 60,
        "",
    ]

    for page in pages:
        blocks.append(f"PAGE CLASS: {page.page_name}")
        blocks.append(f"URL: {page.url}")
        blocks.append(f"TITLE: {page.title}")

        if page.forms:
            blocks.append(f"FORMS: {len(page.forms)}")
            for form in page.forms:
                blocks.append(f"  form[{form.get('id','?')}] — {form.get('fieldSummary','')}")

        blocks.append("ELEMENTS:")
        for el in page.elements:
            _append_element_line(blocks, el, language)

        blocks.append("")

    return "\n".join(blocks)


def _append_element_line(blocks: List[str], el: ElementInfo, language: str):
    strategy = el.best_locator_strategy
    locator = el.best_locator
    label = el.text or el.placeholder or el.aria_label or el.el_name or el.el_id

    if language == "Java Selenium Cucumber":
        var = el.java_var_name
        find_by = _java_find_by(strategy, locator)
        blocks.append(f"  @FindBy({find_by})")
        blocks.append(f"  // type={el.element_type} label='{label[:50]}'")
        blocks.append(f"  WebElement {var};")

    elif language == "Python Behave":
        var = el.python_var_name
        by_expr = _python_by(strategy, locator)
        blocks.append(f"  {var} = ({by_expr})")
        blocks.append(f"  # type={el.element_type} label='{label[:50]}'")

    elif language == "C# SpecFlow":
        var = el.java_var_name[0].upper() + el.java_var_name[1:]
        finds_by = _csharp_finds_by(strategy, locator)
        blocks.append(f"  [{finds_by}]")
        blocks.append(f"  // type={el.element_type} label='{label[:50]}'")
        blocks.append(f"  public IWebElement {var} {{ get; set; }}")

    blocks.append("")


def _java_find_by(strategy: str, locator: str) -> str:
    locator = locator.replace('"', '\\"')
    mapping = {
        "id": f'id = "{locator}"',
        "name": f'name = "{locator}"',
        "css": f'css = "{locator}"',
        "xpath": f'xpath = "{locator}"',
        "link_text": f'linkText = "{locator}"',
    }
    return mapping.get(strategy, f'css = "{locator}"')


def _python_by(strategy: str, locator: str) -> str:
    locator = locator.replace("'", "\\'")
    mapping = {
        "id": f"By.ID, '{locator}'",
        "name": f"By.NAME, '{locator}'",
        "css": f"By.CSS_SELECTOR, '{locator}'",
        "xpath": f"By.XPATH, '{locator}'",
        "link_text": f"By.LINK_TEXT, '{locator}'",
    }
    return mapping.get(strategy, f"By.CSS_SELECTOR, '{locator}'")


def _csharp_finds_by(strategy: str, locator: str) -> str:
    locator = locator.replace('"', '\\"')
    mapping = {
        "id": f'FindsBy(How.Id, Using = "{locator}")',
        "name": f'FindsBy(How.Name, Using = "{locator}")',
        "css": f'FindsBy(How.CssSelector, Using = "{locator}")',
        "xpath": f'FindsBy(How.XPath, Using = "{locator}")',
        "link_text": f'FindsBy(How.LinkText, Using = "{locator}")',
    }
    return mapping.get(strategy, f'FindsBy(How.CssSelector, Using = "{locator}")')


def elements_to_step_context(pages: List[PageInfo]) -> str:
    """
    Compact locator reference passed to the step-definition generator so
    it can embed real locators instead of placeholders.
    """
    lines = ["REAL LOCATORS FROM DOM EXTRACTION:", ""]
    for page in pages:
        lines.append(f"# {page.page_name} ({page.url})")
        for el in page.elements:
            strategy = el.best_locator_strategy
            locator = el.best_locator
            label = el.text or el.placeholder or el.aria_label or el.el_name or el.el_id or "?"
            lines.append(
                f"  {el.element_type}: '{label[:50]}' → {strategy}={locator}"
            )
        lines.append("")
    return "\n".join(lines)
