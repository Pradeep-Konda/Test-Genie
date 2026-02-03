from dotenv import load_dotenv
from datetime import datetime
import os
import traceback
from pathspec import PathSpec
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from nodes.prompts.prompt_loader_bdd import PromptLoader

class CodeAnalysisNode:
    def __init__(self):
        load_dotenv()
        model = os.getenv("MODEL", "gpt-4.1")
        
        self.llm = ChatOpenAI(model=model, temperature=0)
        # print(self.llm.invoke("Ping"))


    # def read_all_files(self, files: list[FilePayload]):
    #     """
    #     Reads project files.
    #     Returns list of dicts with chunk content.
    #     """
    #     try:
    #         output_chunks = []

    #         for f in files:
    #             output_chunks.append({
    #                 "chunk": f.content
    #             })

    #         return output_chunks

    #     except Exception:
    #         pass
    
    def read_all_files(self, project_path: str, chunk_size: int = 15000):
        """
        Reads project files recursively, honoring .gitignore rules.
        Splits files into safe chunks for LLM consumption.
        Returns: list of {file, chunk}
        """

        # Load .gitignore patterns
        gitignore_path = os.path.join(project_path, ".gitignore")
        ignore_spec = None

        if os.path.exists(gitignore_path):
            with open(gitignore_path, "r", encoding="utf-8") as gi:
                ignore_spec = PathSpec.from_lines("gitwildmatch", gi.readlines())

        supported_exts = (
        ".py", ".js", ".ts", ".java", ".go", ".cs",
        ".json", ".yaml", ".yml", ".xml",
        ".env", ".ini", ".cfg", ".properties",
        ".md", ".txt",
        ".sh", ".ps1"
    )

        output_chunks = []

        for root, _, files in os.walk(project_path):
            for f in files:
                file_path = os.path.join(root, f)
                rel_path = os.path.relpath(file_path, project_path)

                # Skip gitignored files
                if ignore_spec and ignore_spec.match_file(rel_path):
                    continue

                # Skip unsupported file types
                if not f.endswith(supported_exts):
                    continue

                try:
                    with open(file_path, "r", encoding="utf-8") as file:
                        content = file.read()

                    # Chunk the file content
                    for i in range(0, len(content), chunk_size):
                        output_chunks.append({
                            "file": file_path,
                            "chunk": content[i:i + chunk_size]
                        })
                        #print(f"Read chunk: {file_path} ({i}–{i + chunk_size})")

                except Exception as e:
                    print(f"Could not read file {file_path}: {e}")
                    continue

        return output_chunks


    async def analyze_chunks(self, chunks):
        """
        Process each chunk with the chunk-agent.
        """
        try:
            self.system_prompt = PromptLoader().prompt_loader("bdd/chunk_agent.jinja")
            results = []

            for idx, item in enumerate(chunks):
                messages = [
                    SystemMessage(content=self.system_prompt),
                    HumanMessage(
                        content=f"Analyze chunk {idx + 1}/{len(chunks)}.\n"
                                f"Extract only API-related information.\n\n"
                                f"{item['chunk']}\n"
                    )
                ]

                result = await self.llm.ainvoke(messages)

                api_text = ""
                if isinstance(result, dict) and "messages" in result:
                    ai_msgs = [
                        m for m in result["messages"]
                        if getattr(m, "type", None) == "ai" or m.__class__.__name__ == "AIMessage"
                    ]
                    api_text = ai_msgs[-1].content if ai_msgs else ""
                elif hasattr(result, "content"):
                    api_text = result.content
                elif isinstance(result, str):
                    api_text = result
                else:
                    api_text = str(result or "")

                results.append(api_text)

            return results

        except Exception as e:
            raise RuntimeError("Error in analyze_chunks", e)


    async def combine_results(self, chunk_results):
        """
        Combine chunk-level results into one OpenAPI document.
        """
        try:
            self.system_prompt = PromptLoader().prompt_loader("bdd/final_agent.jinja")

            combined_text = "\n\n".join(chunk_results)

            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(
                    content=(
                        "Combine all extracted API information into final "
                        "OpenAPI 3.0 version specification YAML:\n\n"
                        f"{combined_text}"
                    )
                )
            ]

            result = await self.llm.ainvoke(messages)

            yaml_text = ""
            if isinstance(result, dict) and "messages" in result:
                ai_msgs = [
                    m for m in result["messages"]
                    if getattr(m, "type", None) == "ai" or m.__class__.__name__ == "AIMessage"
                ]
                yaml_text = ai_msgs[-1].content if ai_msgs else ""
            elif hasattr(result, "content"):
                yaml_text = result.content
            elif isinstance(result, str):
                yaml_text = result
            else:
                yaml_text = str(result or "")

            return yaml_text

        except Exception as e:
            raise RuntimeError("Error in combine results method") from e

    def save_openapi_file(self, project_path: str, yaml_content: str) -> str:
        """Save generated OpenAPI YAML inside the same project folder."""
        output_dir = os.path.join(project_path, "output")
        os.makedirs(output_dir, exist_ok=True)
        filename = "openapi.yaml"
        file_path = os.path.join(output_dir, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(yaml_content)
            
            
    async def __call__(self, data):
        try:
            source_path = data.project_path

            openapi_path = os.path.join(source_path, "output", "openapi.yaml")

            if os.path.exists(openapi_path):
                # Read and return existing OpenAPI spec
                with open(openapi_path, "r", encoding="utf-8") as f:
                    existing_spec = f.read()
                data.analysis = existing_spec
                return data
            

            try:
                chunks = self.read_all_files(source_path)
            except Exception as e:
                raise RuntimeError("Failed while reading all source files") from e

            try:
                chunk_results = await self.analyze_chunks(chunks)
            except Exception as e:
                raise RuntimeError("LLM analysis_chunks method failed") from e

            try:
                final_openapi = await self.combine_results(chunk_results)
            except Exception as e:
                raise RuntimeError("combine results method failed in code analysis") from e
            
            self.save_openapi_file(source_path, final_openapi)
            data.analysis = final_openapi
            return data

        except Exception:
            data.analysis = None
            raise
