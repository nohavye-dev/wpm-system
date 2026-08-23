// Leading options-object convention shared by every add* method:
// add("item") appends, add({before: true}, "item") prepends — prompts stay
// manipulable after instanciation (see clone() on each class).
export type AddOptions = { before?: boolean };

function addItemArgs(first: string | AddOptions, rest: string[]): { items: string[]; before: boolean } {
    if (first !== null && typeof first === "object") {
        return { items: rest, before: Boolean(first.before) };
    }
    return { items: [first, ...rest], before: false };
}

export class PromptTask {
    public constructor(
        public name: string,
        public instructions: string[] = [],
        public constraints: string[] = [],
    ) {}

    public addInstruction(first: string | AddOptions, ...rest: string[]): this {
        const { items, before } = addItemArgs(first, rest);
        if (before) this.instructions.unshift(...items);
        else this.instructions.push(...items);
        return this;
    }

    public addConstraint(first: string | AddOptions, ...rest: string[]): this {
        const { items, before } = addItemArgs(first, rest);
        if (before) this.constraints.unshift(...items);
        else this.constraints.push(...items);
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

    public addPurpose(first: string | AddOptions, ...rest: string[]): this {
        const { items, before } = addItemArgs(first, rest);
        if (before) this.purpose.unshift(...items);
        else this.purpose.push(...items);
        return this;
    }

    public addInstruction(first: string | AddOptions, ...rest: string[]): this {
        const { items, before } = addItemArgs(first, rest);
        if (before) this.instructions.unshift(...items);
        else this.instructions.push(...items);
        return this;
    }

    public addTask(task: PromptTask): this {
        this.tasks.push(task);
        return this;
    }

    public addExpectedBehavior(first: string | AddOptions, ...rest: string[]): this {
        const { items, before } = addItemArgs(first, rest);
        if (before) this.expectedBehavior.unshift(...items);
        else this.expectedBehavior.push(...items);
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


// Generic wrapper for deterministic data pushes (project rules, RAG pop-in)
// spliced into the system prompt via experimental.chat.system.transform.
// Asymmetry per docs/internals/feature-hybride-rag.md: setBody carries
// server-pre-rendered text (byte-identical with the resource), addItems
// carries client-composed entries. A block without a tag renders its
// content raw — used for project rules, whose server rendering already
// provides the <project-rules> wrapper.
export class InjectionBlock {
    public constructor(
        public tag?: string,
        public title?: string,
        public purpose: string[] = [],
        public body?: string,
        public items: string[] = [],
        public notes: string[] = [],
    ) {}

    public addPurpose(first: string | AddOptions, ...rest: string[]): this {
        const { items, before } = addItemArgs(first, rest);
        if (before) this.purpose.unshift(...items);
        else this.purpose.push(...items);
        return this;
    }

    // Pre-rendered content pushed verbatim (no re-indentation, no drift).
    public setBody(text: string): this {
        this.body = text;
        return this;
    }

    public addItem(first: string | AddOptions, ...rest: string[]): this {
        const { items, before } = addItemArgs(first, rest);
        if (before) this.items.unshift(...items);
        else this.items.push(...items);
        return this;
    }

    public addNote(first: string | AddOptions, ...rest: string[]): this {
        const { items, before } = addItemArgs(first, rest);
        if (before) this.notes.unshift(...items);
        else this.notes.push(...items);
        return this;
    }

    public clone(): InjectionBlock {
        return new InjectionBlock(
            this.tag,
            this.title,
            [...this.purpose],
            this.body,
            [...this.items],
            [...this.notes],
        );
    }

    public isEmpty(): boolean {
        return !this.body?.trim() && this.items.length === 0;
    }

    public toString(): string {
        if (!this.tag) {
            return [this.body?.trim() ?? "", ...this.items].filter(Boolean).join("\n");
        }

        const lines: string[] = [`<${this.tag}>`];

        if (this.title) {
            lines.push(`## ${this.title}`, "");
        }

        if (this.purpose.length > 0) {
            lines.push("## Purpose", "");
            for (const item of this.purpose) {
                lines.push(`  - ${item}`);
            }
            lines.push("");
        }

        for (const item of this.items) {
            lines.push(`- ${item}`);
        }

        if (this.body?.trim()) {
            if (this.items.length > 0) lines.push("");
            lines.push(this.body.trim());
        }

        if (this.notes.length > 0) {
            if (this.items.length > 0 || this.body?.trim()) lines.push("");
            lines.push("## Notes", "");
            for (const note of this.notes) {
                lines.push(`  - ${note}`);
            }
        }

        lines.push("");
        lines.push(`</${this.tag}>`);

        return lines.join("\n");
    }
}
