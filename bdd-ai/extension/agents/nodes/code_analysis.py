from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime
import os
import glob
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.agents import create_agent
from pathspec import PathSpec
from langchain_openai import ChatOpenAI

class CodeAnalysisNode:
    def __init__(self):
        load_dotenv()
        model = os.getenv("MODEL", "gpt-4.1")

        self.llm = ChatOpenAI(
            model=model,
            temperature=0,
        )

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

    def build_chunk_agent(self):
        """
        Agent used for processing single chunks of code.
        """
        self.system_prompt = (
            "You are an API extraction agent. Analyze the given code chunk and extract ONLY explicitly visible API information.\n"
            "\n"
            "OUTPUT FORMAT (use this exact JSON structure):\n"
            "{\n"
            '  "endpoints": [\n'
            '    {"path": "/users/{id}", "method": "GET", "path_params": ["id"], "query_params": [], "request_body": null, "response_schema": {"type": "object"}, "status_codes": [200, 404]}\n'
            "  ],\n"
            '  "server_hints": {"host": "localhost", "port": 8000, "base_path": "/api"},\n'
            '  "models": [\n'
            '    {"name": "User", "fields": [{"name": "id", "type": "integer"}, {"name": "email", "type": "string"}]}\n'
            "  ]\n"
            "}\n"
            "\n"
            "EXTRACTION RULES:\n"
            "- Extract ONLY what is explicitly visible in the code\n"
            "- Detect server config from app.run(), listen(), server.port, UseUrls(), etc.\n"
            "- Parse model definitions from classes, dataclasses, Pydantic, structs, interfaces\n"
            "- Use null for any field not visible in the chunk\n"
            "- Return valid JSON only — no markdown, no explanations, no invented data\n"
        )


        return create_agent(
            model=self.llm,
            tools=[],
            system_prompt=self.system_prompt
        )

    def build_final_agent(self):
        """
        Agent to merge all chunk results into a final OpenAPI spec.
        """
        self.system_prompt = (
            "You are an OpenAPI 3.0 specification generator. Merge the extracted API data into a complete, valid YAML specification.\n"
            "\n"
            "REQUIRED SECTIONS:\n"
            "1. openapi: '3.0.0'\n"
            "2. info: title, version, description\n"
            "3. servers: Use detected host/port (default: http://localhost:8000)\n"
            "4. paths: All endpoints with methods, parameters, requestBody, responses\n"
            "5. components/schemas: All data models with types, properties, required fields, examples\n"
            "\n"
            "SCHEMA RULES:\n"
            "- Include 'type', 'properties', 'required' for every object schema\n"
            "- Use $ref for reusable schemas in components/schemas\n"
            "- Add realistic 'example' values for all fields\n"
            "- Define responses for success (2xx) and error (4xx, 5xx) cases\n"
            "\n"
            "OUTPUT RULES:\n"
            "- Return ONLY valid OpenAPI 3.0 YAML — no markdown code blocks\n"
            "- Start directly with 'openapi:' — no explanations before or after\n"
            "- Do NOT invent endpoints or fields not present in the extracted data\n"
        )


        return create_agent(
            model=self.llm,
            tools=[],
            system_prompt=self.system_prompt,
        )

    def analyze_chunks(self, chunks):
        """
        Process each chunk with the chunk-agent.
        """
        agent = self.build_chunk_agent()
        results = []

        for idx, item in enumerate(chunks):
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(
                    content=f"Analyze chunk {idx + 1}/{len(chunks)} from file: {item['file']}.\n"
                    "Extract only API-related information.\n\n"
                    f"```\n{item['chunk']}\n```"
                )
            ]

            result = agent.invoke({"messages": messages})
            #print(result, "result of chunk analysis")

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
            
            #print(api_text, "api_text extracted")

            results.append(api_text)

        return results

    def combine_results(self, chunk_results):
        """
        Combine chunk-level results into one OpenAPI doc.
        """
        agent = self.build_final_agent()

        combined_text = "\n\n".join(chunk_results)

        messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(
                content=f"Combine all extracted API information into final OpenAPI 3.0 version specification Yaml:\n\n{combined_text}"
            )
        ]

        result = agent.invoke({"messages": messages})

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
        
        #print(yaml_text, "final OpenAPI yaml")

        return yaml_text
    
    def save_openapi_file(self, project_path: str, yaml_content: str) -> str:
        """Save generated OpenAPI YAML inside the same project folder."""
        output_dir = os.path.join(project_path, "output")
        os.makedirs(output_dir, exist_ok=True)
        filename = "openapi.yaml"
        file_path = os.path.join(output_dir, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(yaml_content)
        
    

    def __call__(self, data):
        source_path = data.project_path

        openapi_path = os.path.join(source_path, "output", "openapi.yaml")

        if os.path.exists(openapi_path):
            # Read and return existing OpenAPI spec
            with open(openapi_path, "r", encoding="utf-8") as f:
                existing_spec = f.read()
            data.analysis = existing_spec
            return data

        # Step 1: read all files & chunk
        chunks = self.read_all_files(source_path)
        #print(chunks, "read chunks")

        # Step 2: analyze each chunk
        chunk_results = self.analyze_chunks(chunks)

        #print(chunk_results)

        # Step 3: combine all into final OpenAPI
        final_openapi = self.combine_results(chunk_results)

        #print(final_openapi, "final OpenAPI spec")

        self.save_openapi_file(source_path, final_openapi)

        data.analysis = final_openapi

        return data
