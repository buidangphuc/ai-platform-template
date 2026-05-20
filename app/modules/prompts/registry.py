from langchain_core.prompts import ChatPromptTemplate
from langchain_core.prompts.prompt import PromptTemplate as LangChainPromptTemplate

from app.modules.prompts.schemas import PromptRender, PromptTemplate


class InMemoryPromptRegistry:
    def __init__(self) -> None:
        self._templates: dict[tuple[str, str], PromptTemplate] = {}
        self._latest_versions: dict[str, str] = {}

    @classmethod
    def with_defaults(cls) -> "InMemoryPromptRegistry":
        registry = cls()
        registry.register(
            PromptTemplate(
                name="rag.answer",
                version="v1",
                template=(
                    "Answer the question using only the provided context.\n\n"
                    "Question: {question}\n\n"
                    "Context:\n{context}"
                ),
                variables=["question", "context"],
                metadata={"capability": "rag"},
            )
        )
        return registry

    def register(self, template: PromptTemplate) -> None:
        key = (template.name, template.version)
        self._templates[key] = template
        self._latest_versions[template.name] = template.version

    def render(
        self,
        name: str,
        *,
        variables: dict[str, object],
        version: str | None = None,
    ) -> PromptRender:
        template = self.get(name, version=version)
        missing = [
            variable for variable in template.variables if variable not in variables
        ]
        if missing:
            raise ValueError(f"Missing prompt variables: {', '.join(missing)}")

        content = template.template.format(**variables)
        return PromptRender(
            name=template.name,
            version=template.version,
            content=content,
            variables=variables,
            metadata=template.metadata,
        )

    def get_langchain_prompt(
        self,
        name: str,
        *,
        version: str | None = None,
    ) -> ChatPromptTemplate | LangChainPromptTemplate:
        template = self.get(name, version=version)
        if template.template_type == "string":
            return LangChainPromptTemplate.from_template(template.template)
        messages = template.messages or [("human", template.template)]
        return ChatPromptTemplate.from_messages(messages)

    def get(self, name: str, *, version: str | None = None) -> PromptTemplate:
        resolved_version = version or self._latest_versions.get(name)
        if resolved_version is None:
            raise KeyError(f"Prompt not found: {name}")
        key = (name, resolved_version)
        if key not in self._templates:
            raise KeyError(f"Prompt not found: {name}@{resolved_version}")
        return self._templates[key]
