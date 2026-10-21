---
name: generate-metadata
version: 1.2.0
description: Generate and validate frontmatter metadata for markdown transcriptions and voice notes. Use when processing raw transcriptions, enriching Letterly notes, or preparing notes before moving them to final outputs.
---

# Generate Metadata

Use this skill to turn a raw markdown transcription into a structured Obsidian note with queryable top-level frontmatter.

The agent owns judgment. The script owns structure.

- The agent reads the note and decides what the metadata should say.
- The script merges the metadata into YAML frontmatter and validates shape.
- The script does not call an AI API and cannot infer metadata by itself.

## Core Outcome

For each target markdown file, produce valid frontmatter metadata that helps Rami later answer:

- What kind of note is this?
- What exact situation does this note capture?
- What problems, fears, beliefs, decisions, and patterns showed up?
- What should Rami actually do differently?
- Which people, projects, and concepts should be linked in Obsidian?

Preserve existing frontmatter such as `Status`, `tags`, `letterly_tags`, `Links`, and `Created`. Overwrite only the managed metadata fields.

## Managed Fields

The script manages these top-level frontmatter fields:

- `metadata_schema_version`
- `metadata_generated_at`
- `note_types`
- `summary`
- `core_themes`
- `practical_takeaways`
- `communication_flaws`
- `relationship_patterns`
- `identity_beliefs`
- `recurring_fears`
- `decision_principles`
- `open_problems`
- `experiments_to_run`
- `people_mentioned`
- `projects_mentioned`

Use strings and lists of strings only. Do not generate nested objects.

Only field names and `note_types` use snake_case. Every other metadata value must be natural language that makes sense when read by a human in Obsidian.

Do not write tag-slugs as metadata values. Values like `fear_of_missing_the_one`, `getting_too_far_ahead_in_your_head`, `instant_attachment`, or `overprojecting_future_family_onto_someone_unknown` are bad because they are annoying to read and do not match how Rami thinks.

Write readable phrases instead:

- `fear of missing the one`
- `getting too far ahead in your head`
- `instant attachment`
- `overprojecting a future family onto someone unknown`

If a value would look stupid in a sentence or in Obsidian Properties, rewrite it as a phrase.

## Allowed Note Types

Read the current allowed values from `schema.json` when unsure. Current values:

- `self_reflection`
- `problem_solving`
- `emotional_processing`
- `communication_analysis`
- `relationship_family`
- `product_entrepreneurship`
- `content_idea`
- `task_planning`
- `career_work`
- `life_philosophy`

Use `note_types` as a list. Each note needs at least one value. Use multiple values when the note blends categories.

## Letterly Tags Context

When frontmatter includes `letterly_tags`, treat those values as source context from Letterly. They can clarify the note's intended bucket, such as `journal`, `ideas`, `purpose`, or `chalant`.

Use them as a hint, not as proof. The transcription body remains the source of truth. If a Letterly tag conflicts with the body, follow the body.

Do not copy Letterly tag slugs directly into generated metadata unless they are already natural human-readable phrases. Convert them into useful phrases in generated fields, and only when the note content supports them.

Do not include `letterly_tags` in the JSON payload for this script. The process step writes it, and the merge script preserves it as non-managed frontmatter.

## How To Read A Note

Treat the main transcription body as the source of truth. Existing `letterly_tags`, `## Connections`, `## Related Notes`, frontmatter, and wiki-links are useful context, but the metadata should describe what Rami actually said in the note.

When a note rambles across several topics, identify the main job the note is doing. Common jobs in Rami's notes:

- debugging a personal problem
- processing an emotional event
- extracting a lesson from a social or work interaction
- thinking through a product or entrepreneurship direction
- turning a lived experience into content
- clarifying values, identity, purpose, or life philosophy
- making a plan or deciding what to do next

Do not summarize the note as if it were a neutral article. Write metadata for future Rami trying to remember, search, and act on his own spoken thoughts.

## Field Guidance

`summary`

Write a medium-sized, specific summary. It should be enough for Rami to recognize the exact note without opening it. Mention the concrete situation, not just the abstract theme.

Good:
`Reflection after the Purpose interview where Rami notices that feeling in control makes his communication smoother, then turns that into an Audora product direction around pre-meeting preparation.`

Weak:
`A note about communication and product ideas.`

`core_themes`

Use descriptive phrases, not generic tags. Prefer `feeling in control before high-stakes conversations` over `control`.

`practical_takeaways`

Write direct commands to Rami. Make them personalized to his actual patterns and problems.

Good:
`Prepare the first minute before important conversations so you do not enter the meeting feeling vague or powerless.`

Weak:
`Preparing for conversations can be useful.`

`communication_flaws`

Use blunt readable phrases when the note reveals a communication issue. Examples:

- `overexplaining`
- `approval seeking`
- `avoiding direct conflict`
- `delayed response`
- `performing confidence instead of being clear`

`relationship_patterns`

Capture patterns involving family, friends, romantic interest, social approval, loyalty, attachment, boundaries, or repeated interpersonal behavior.

`identity_beliefs`

Capture beliefs Rami expresses about himself, his role, his purpose, his limitations, or what kind of person he is. These can be full sentences when needed.

`recurring_fears`

Use readable phrases for fears and anxieties. Examples:

- `fear of rejection`
- `fear of losing control`
- `fear of wasting potential`
- `fear of being misunderstood`
- `fear that opportunities will disappear`

`decision_principles`

Capture reusable rules Rami seems to be forming, especially around work, product, relationships, communication, time, purpose, or risk.

`open_problems`

Write unresolved questions or problems the note raises. Use clear natural language.

`experiments_to_run`

Write concrete tests Rami can try. These should be action-oriented and small enough to execute.

`people_mentioned`

Use Obsidian wiki-links when names are clear, for example `[[Connor]]`. Keep people out if the note only says generic groups like "people" or "women" unless the concept itself should be linked elsewhere.

`projects_mentioned`

Use wiki-links for concrete projects, companies, apps, communities, content projects, or ventures, for example `[[Audora]]`, `[[Purpose]]`, `[[The Chalant Society]]`.

## Wiki-Link Policy

Prefer wiki-links wherever they improve future navigation. Use them in any field, not only people/projects.

Use existing links from the note body when they fit. If a concept clearly deserves to become a note but may not exist yet, still use a wiki-link. Avoid over-linking generic words that do not help future search.

Good:
`Build [[Audora]] around pre-meeting control instead of generic meeting transcription.`

Weak:
`Build [[software]] around [[things]] and [[people]].`

## Execution Protocol

1. Resolve target files from the user request.
2. Read each full markdown file.
3. Extract metadata for each file using every managed field.
4. Put empty arrays in list fields with no signal.
5. Write the metadata payload to a new file that no other run can use: create it with `mktemp /tmp/generate-metadata-XXXXXX.json`. Never reuse a fixed name such as `/tmp/metadata-batch.json`. Parallel agents that share a file overwrite each other's payloads.
6. Run the bundled script to merge metadata into frontmatter.
7. Run validation after applying metadata.
8. Report which files passed and which failed.
9. Treat the JSON payload as a temporary handoff file; do not store it beside the note or in the vault unless the user explicitly asks for debugging output.

For one file:

```bash
/Users/rami/Documents/life-os/ai-agents-config/skills/.venv/bin/python /Users/rami/Documents/life-os/ai-agents-config/skills/generate-metadata/scripts/generate_metadata.py apply path/to/note.md --metadata-file /tmp/metadata.json
/Users/rami/Documents/life-os/ai-agents-config/skills/.venv/bin/python /Users/rami/Documents/life-os/ai-agents-config/skills/generate-metadata/scripts/generate_metadata.py validate path/to/note.md
```

For many files:

```bash
/Users/rami/Documents/life-os/ai-agents-config/skills/.venv/bin/python /Users/rami/Documents/life-os/ai-agents-config/skills/generate-metadata/scripts/generate_metadata.py apply-batch /tmp/metadata-batch.json
/Users/rami/Documents/life-os/ai-agents-config/skills/.venv/bin/python /Users/rami/Documents/life-os/ai-agents-config/skills/generate-metadata/scripts/generate_metadata.py validate path/to/one.md path/to/two.md
```

To inspect the current schema:

```bash
/Users/rami/Documents/life-os/ai-agents-config/skills/.venv/bin/python /Users/rami/Documents/life-os/ai-agents-config/skills/generate-metadata/scripts/generate_metadata.py schema
```

## Payload Format

Single-file payload:

```json
{
  "note_types": ["communication_analysis", "product_entrepreneurship"],
  "summary": "Reflection after a strong Purpose interview where Rami notices that feeling in control makes his communication smoother, then converts that insight into an Audora direction around pre-meeting preparation.",
  "core_themes": [
    "feeling in control before high-stakes conversations",
    "using personal communication struggles as product insight"
  ],
  "practical_takeaways": [
    "Prepare the first minute before important conversations so you enter with control instead of vagueness.",
    "Test [[Audora]] with one narrow pre-meeting use case before exploring mid-meeting feedback."
  ],
  "communication_flaws": [
    "fear of losing control mid-conversation",
    "overexplaining when your self-concept feels unclear"
  ],
  "relationship_patterns": [],
  "identity_beliefs": [
    "I communicate best when I feel in control of how I explain myself and my work."
  ],
  "recurring_fears": [
    "fear of becoming your old self in high-pressure conversations"
  ],
  "decision_principles": [
    "Start with the smallest product test that proves the emotional behavior."
  ],
  "open_problems": [
    "How can [[Audora]] help someone feel in control before a meeting without becoming another generic note-taker?"
  ],
  "experiments_to_run": [
    "Run mock interviews immediately before real interviews and track whether the first minute feels more controlled."
  ],
  "people_mentioned": ["[[Connor]]"],
  "projects_mentioned": ["[[Audora]]", "[[Purpose]]"]
}
```

Batch payload:

```json
{
  "files": [
    {
      "path": "unprocessed/Example.md",
      "metadata": {
        "note_types": ["self_reflection"],
        "summary": "Specific summary of this note.",
        "core_themes": [],
        "practical_takeaways": [],
        "communication_flaws": [],
        "relationship_patterns": [],
        "identity_beliefs": [],
        "recurring_fears": [],
        "decision_principles": [],
        "open_problems": [],
        "experiments_to_run": [],
        "people_mentioned": [],
        "projects_mentioned": []
      }
    }
  ]
}
```

The script fills `metadata_schema_version` and `metadata_generated_at`; the agent does not need to provide them.

The markdown frontmatter is the source of truth after a successful merge. The JSON payload is only an intermediate file for the script.

## Failure Behavior

If validation fails, leave the file where it is and report the validation errors. Do not move the file. Do not delete content. Do not rewrite unrelated frontmatter to fix style.

If a note is too vague to infer a field, use an empty array for that list field. Do not invent people, projects, or decisions.

## Quality Bar

A good output should feel useful six months later. It should be compact enough for Obsidian Properties and Dataview, but specific enough that Rami can search his vault and immediately understand why the note matters.

Avoid generic coaching language. Extract what is actually present in the note, then turn only the actionable parts into personalized commands.
