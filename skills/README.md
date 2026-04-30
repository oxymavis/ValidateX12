# Skills layout for external agents

Point **`{skills_dir}`** at this directory (`…/Validation EDI/skills/`). Expected shape:

```text
skills/
  ├── edi-validate-studio/
  │   └── SKILL.md
  └── …
```

Each immediate child of `skills/` is one skill folder; that folder must contain **`SKILL.md`**.

Cursor also resolves `.cursor/skills/edi-validate-studio/SKILL.md` as a symlink to `skills/edi-validate-studio/SKILL.md`.
