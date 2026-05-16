---
name: gsd:cleanup
description: Archive accumulated phase directories from completed milestones
allowed-tools:
  - Read
  - Write
  - Bash
  - AskUserQuestion
requires: [phase]
---
<objective>
Archive phase directories from completed milestones into `.planning/milestones/v{X.Y}-phases/`.

Use when `.planning/phases/` has accumulated directories from past milestones.
</objective>

<execution_context>
@c:/Users/1/Desktop/Cursor/VSKS_CRM/.claude/get-shit-done/workflows/cleanup.md
</execution_context>

<process>
Execute end-to-end.
Identify completed milestones, show a dry-run summary, and archive on confirmation.
</process>
