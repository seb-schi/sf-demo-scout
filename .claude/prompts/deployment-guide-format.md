# Deployment Guide Format

Read this on demand at Step 5 (writing the deployment guide). The format and rules below are authoritative.

## Format

```markdown
# Pipeline Change — [Topic]
Date: [YYYY-MM-DD] [HHmm]
Approved by: SE (during /project-sparring session)

## Summary
[1-2 sentences: what changes and why]

## Files to Create
- [path]: [description of contents]
  ```
  [full file content — no placeholders, no "add something like this"]
  ```

## Files to Modify
- [path]: [what changes]
  - Find: [exact text to find]
  - Replace: [exact replacement text]

## Files to Delete
- [path]: [why]

## Verification
- [How to confirm the change worked — what to test, what to check]

## Rollback
- [How to undo if something breaks]
```

## Rules

- Every file change must be mechanically executable — no ambiguity, no judgment calls
- Use exact find/replace pairs, not "update the section about X"
- Include full file contents for new files — Sonnet should not need to invent anything
- The guide is the single source of truth — do not leave decisions for Sonnet to make
