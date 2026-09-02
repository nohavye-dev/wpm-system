from dataclasses import dataclass, field


@dataclass
class PromptTask:
    name: str
    instructions: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    expected_behavior: list[str] = field(default_factory=list)

    def add_instruction(self, *items: str) -> "PromptTask":
        self.instructions.extend(items)
        return self

    def add_constraint(self, *items: str) -> "PromptTask":
        self.constraints.extend(items)
        return self

    def add_expected_behavior(self, *items: str) -> "PromptTask":
        self.expected_behavior.extend(items)
        return self

    def clone(self) -> "PromptTask":
        return PromptTask(
            self.name,
            self.instructions.copy(),
            self.constraints.copy(),
            self.expected_behavior.copy(),
        )

    def to_string(self, level: int = 2) -> str:
        heading = "#" * level
        constraint_heading = "#" * (level + 1)
        indent = "  " * (level - 1)
        item_indent = "  " * level

        lines: list[str] = [
            f"{heading}# {self.name}",
            "",
        ]

        for instruction in self.instructions:
            lines.append(f"{indent}- {instruction}")

        if self.constraints:
            lines.extend(
                [
                    "",
                    f"{constraint_heading} Constraints",
                    "",
                ]
            )

            for constraint in self.constraints:
                lines.append(f"{item_indent}- {constraint}")

        if self.expected_behavior:
            lines.extend(
                [
                    "",
                    f"{constraint_heading} Expected behavior",
                    "",
                ]
            )

            for item in self.expected_behavior:
                lines.append(f"{item_indent}- {item}")

        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_string()


@dataclass
class PromptContext:
    tag: str = "opencode_plugin_context"
    purpose: list[str] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)
    tasks: list[PromptTask] = field(default_factory=list)
    expected_behavior: list[str] = field(default_factory=list)

    def add_purpose(self, *items: str) -> "PromptContext":
        self.purpose.extend(items)
        return self

    def add_instruction(self, *items: str) -> "PromptContext":
        self.instructions.extend(items)
        return self

    def add_task(self, task: PromptTask) -> "PromptContext":
        self.tasks.append(task)
        return self

    def add_expected_behavior(self, *items: str) -> "PromptContext":
        self.expected_behavior.extend(items)
        return self

    def clone(self) -> "PromptContext":
        return PromptContext(
            self.tag,
            self.purpose.copy(),
            self.instructions.copy(),
            [task.clone() for task in self.tasks],
            self.expected_behavior.copy(),
        )

    def to_string(self) -> str:
        lines: list[str] = [
            f"<{self.tag}>",
        ]

        if self.purpose:
            lines.extend(
                [
                    "## Purpose",
                    "",
                    *(f"  - {item}" for item in self.purpose),
                    "",
                ]
            )

        if self.instructions or self.tasks:
            lines.extend(
                [
                    "## Instructions",
                    "",
                ]
            )

            for instruction in self.instructions:
                lines.append(f"  - {instruction}")

            if self.instructions and self.tasks:
                lines.append("")

            for index, task in enumerate(self.tasks):
                lines.append(task.to_string(3))

                if index < len(self.tasks) - 1:
                    lines.append("")

            lines.append("")

        if self.expected_behavior:
            lines.extend(
                [
                    "## Expected behavior",
                    "",
                    *(f"  - {item}" for item in self.expected_behavior),
                    "",
                ]
            )

        lines.append(f"</{self.tag}>")

        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_string()
