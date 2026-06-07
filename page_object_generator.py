from services.azure_openai_service import AzureOpenAIService
from services.web_crawler import PageInfo
from services.dom_extractor import pages_to_pom_context
from prompts.page_object_prompt import JAVA_SYSTEM, PYTHON_SYSTEM, CSHARP_SYSTEM, USER_TEMPLATE
from utils.helpers import clean_code_output
from utils.logger import AppLogger

logger = AppLogger.get_logger("agent.page_object_generator")

_SYSTEMS = {
    "Java Selenium Cucumber": JAVA_SYSTEM,
    "Python Behave": PYTHON_SYSTEM,
    "C# SpecFlow": CSHARP_SYSTEM,
}


class PageObjectGeneratorAgent:
    """
    Generates Page Object Model classes from crawled DOM data + step definitions.

    For each page in `pages`, produces one POM class containing:
      - All element declarations with real locators (@FindBy / By.* / [FindsBy])
      - Action methods that the step definitions expect
    """

    def __init__(self, openai_service: AzureOpenAIService):
        self.svc = openai_service

    def generate(
        self,
        pages: list[PageInfo],
        step_definitions: str,
        language: str = "Java Selenium Cucumber",
    ) -> dict[str, str]:
        """
        Returns a dict mapping filename → code for each generated page object.
        """
        logger.info(f"PageObjectGeneratorAgent: generating for {len(pages)} page(s) in {language}")

        system = _SYSTEMS.get(language, JAVA_SYSTEM)
        results: dict[str, str] = {}

        for page in pages:
            logger.info(f"Generating page object for: {page.page_name}")

            pom_context = pages_to_pom_context([page], language)
            user_msg = USER_TEMPLATE.format(
                page_pom_context=pom_context,
                step_definitions=step_definitions[:3000],
                language=language,
            )

            raw = self.svc.chat_completion(
                messages=[{"role": "user", "content": user_msg}],
                system_prompt=system,
                temperature=0.15,
                max_tokens=3500,
            )
            code = clean_code_output(raw)
            filename = _page_to_filename(page.page_name, language)
            results[filename] = code
            logger.info(f"Page object generated: {filename}")

        return results


def _page_to_filename(page_name: str, language: str) -> str:
    ext = {
        "Java Selenium Cucumber": ".java",
        "Python Behave": ".py",
        "C# SpecFlow": ".cs",
    }.get(language, ".java")

    # Ensure PascalCase + "Page" suffix
    name = page_name if page_name.endswith("Page") else page_name + "Page"
    return name + ext
