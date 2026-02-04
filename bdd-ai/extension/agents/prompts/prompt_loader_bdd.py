# from jinja2 import Template
import os
from typing import Dict, Any, Optional
from jinja2 import Environment, FileSystemLoader, select_autoescape


class PromptLoader:
    """
    Centralized Jinja2 prompt renderer.
    """

    def __init__(self):
        PROMPTS_DIR = os.path.dirname(__file__)
        self.env = Environment(
            loader=FileSystemLoader(PROMPTS_DIR),
            trim_blocks=True,
            lstrip_blocks=True,
            autoescape=select_autoescape(
                enabled_extensions=("html", "htm", "xml", "xhtml"),
                default_for_string=False,
                default=False,
            ),
        )

    def prompt_loader(self,file_name: str,context: Optional[Dict[str, Any]] = None) -> str:
        """
        Reads a jinja template file and return rendered prompt text
        Output: Plain string containing string
        """

        try:
            template = self.env.get_template(file_name)
        except Exception:
            raise FileNotFoundError(f"Unable to load template: {file_name}")

        return template.render(**(context or {}))

