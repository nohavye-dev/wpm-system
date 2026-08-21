export class PromptTask {
    public constructor(
        public name: string,
        public instructions: string[] = [],
        public constraints: string[] = [],
    ) {}

    public addInstruction(...items: string[]): this {
        this.instructions.push(...items);
        return this;
    }

    public addConstraint(...items: string[]): this {
        this.constraints.push(...items);
        return this;
    }

    public clone(): PromptTask {
        return new PromptTask(
            this.name,
            [...this.instructions],
            [...this.constraints],
        );
    }

    public toString(level = 2): string {
        const heading = "#".repeat(level);
        const constraintHeading = "#".repeat(level + 1);
        const indent = "  ".repeat(level - 1);
        const itemIndent = "  ".repeat(level);

        const lines: string[] = [
            `${heading}# ${this.name}`,
            "",
        ];

        for (const instruction of this.instructions) {
            lines.push(`${indent}- ${instruction}`);
        }

        if (this.constraints.length > 0) {
            lines.push("");
            lines.push(`${constraintHeading} Constraints`);
            lines.push("");

            for (const constraint of this.constraints) {
                lines.push(`${itemIndent}- ${constraint}`);
            }
        }

        return lines.join("\n");
    }
}


export class PromptContext {
    public constructor(
        public tag = "opencode_plugin_context",
        public purpose: string[] = [],
        public instructions: string[] = [],
        public tasks: PromptTask[] = [],
        public expectedBehavior: string[] = [],
    ) {}

    public addPurpose(...items: string[]): this {
        this.purpose.push(...items);
        return this;
    }

    public addInstruction(...items: string[]): this {
        this.instructions.push(...items);
        return this;
    }

    public addTask(task: PromptTask): this {
        this.tasks.push(task);
        return this;
    }

    public addExpectedBehavior(...items: string[]): this {
        this.expectedBehavior.push(...items);
        return this;
    }

    public clone(): PromptContext {
        return new PromptContext(
            this.tag,
            [...this.purpose],
            [...this.instructions],
            this.tasks.map(task => task.clone()),
            [...this.expectedBehavior],
        );
    }

    public toString(): string {
        const lines: string[] = [
            `<${this.tag}>`,
        ];

        if (this.purpose.length > 0) {
            lines.push(
                "## Purpose",
                "",
                ...this.purpose.map(item => `  - ${item}`),
                "",
            );
        }

        if (
            this.instructions.length > 0 ||
            this.tasks.length > 0
        ) {
            lines.push("## Instructions", "");

            for (const instruction of this.instructions) {
                lines.push(`  - ${instruction}`);
            }

            if (this.instructions.length > 0 && this.tasks.length > 0) {
                lines.push("");
            }

            for (const [index, task] of this.tasks.entries()) {
                lines.push(task.toString(3));

                if (index < this.tasks.length - 1) {
                    lines.push("");
                }
            }

            lines.push("");
        }

        if (this.expectedBehavior.length > 0) {
            lines.push(
                "## Expected behavior",
                "",
                ...this.expectedBehavior.map(item => `  - ${item}`),
                "",
            );
        }

        lines.push(`</${this.tag}>`);

        return lines.join("\n");
    }
}
