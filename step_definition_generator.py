import re
from typing import List

from services.azure_openai_service import AzureOpenAIService
from services.chroma_service import ChromaService
from prompts.step_definition_prompt import (
    JAVA_SYSTEM,
    PYTHON_SYSTEM,
    CSHARP_SYSTEM,
    USER_TEMPLATE,
)
from utils.helpers import clean_code_output
from utils.logger import AppLogger

logger = AppLogger.get_logger("agent.step_definition_generator")

_SYSTEMS = {
    "Java Selenium Cucumber": JAVA_SYSTEM,
    "Python Behave": PYTHON_SYSTEM,
    "C# SpecFlow": CSHARP_SYSTEM,
}


class StepDefinitionGeneratorAgent:
    """
    Agent 5 — generates production-ready step definitions for a given
    feature file, reusing existing steps from the ChromaDB repository.
    """

    def __init__(self, openai_service: AzureOpenAIService, chroma_service: ChromaService):
        self.svc = openai_service
        self.chroma = chroma_service

    def generate(
        self,
        feature_content: str,
        language: str = "Java Selenium Cucumber",
        page_name: str = "PageObject",
        dom_locator_context: str = "",  # real locators from web crawler
    ) -> str:
        logger.info(f"StepDefinitionGeneratorAgent: generating for {language}")

        similar = self.chroma.search_similar_steps(feature_content, n=5)
        existing = (
            "\n\n---\n".join(s["document"] for s in similar) if similar else "None yet."
        )
        if similar:
            logger.info(f"Found {len(similar)} reusable step definitions in repository")

        if dom_locator_context:
            logger.info("Using real DOM locators from web crawler for accurate step generation")

        system = _SYSTEMS.get(language, JAVA_SYSTEM)

        # Inject DOM locators into the feature content block so the LLM can reference them
        feature_with_dom = feature_content
        if dom_locator_context:
            feature_with_dom = (
                feature_content
                + "\n\n=== REAL DOM LOCATORS (use these — do NOT invent selectors) ===\n"
                + dom_locator_context[:4000]
            )

        user_msg = USER_TEMPLATE.format(
            feature_file_content=feature_with_dom,
            existing_steps=existing,
            language=language,
            page_name=page_name,
        )

        logger.info(f"Calling Azure OpenAI for step definition generation ({language})")
        raw = self.svc.chat_completion(
            messages=[{"role": "user", "content": user_msg}],
            system_prompt=system,
            temperature=0.2,
            max_tokens=4000,
        )
        result = clean_code_output(raw)

        # Persist new step texts for future reuse
        new_steps = self._extract_step_texts(result)
        if new_steps:
            self.chroma.add_steps(new_steps, {"language": language})
            logger.info(f"Stored {len(new_steps)} new step definitions")

        logger.info("StepDefinitionGeneratorAgent: generation complete")
        return result

    # ------------------------------------------------------------------ #

    def _extract_step_texts(self, code: str) -> List[str]:
        """Pull out the regex/string from step annotations for storage."""
        patterns = [
            r'@(?:Given|When|Then|And)\("([^"]+)"\)',   # Java
            r"@(?:Given|When|Then|And)\('([^']+)'\)",   # Java single-quote
            r'@(?:given|when|then)\(["\']([^"\']+)["\']',  # Python
            r'\[(?:Given|When|Then|And)\("([^"]+)"\)\]',   # C#
        ]
        steps: List[str] = []
        for pat in patterns:
            steps.extend(re.findall(pat, code))
        return list(set(steps))
