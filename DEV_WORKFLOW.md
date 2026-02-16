# Development Workflow

This document defines the standard development loop for the CAD Profiler project.

The goal:
Run → Verify → Review → Commit → Push.

---

# Standard Change Loop (After Cursor Edits)

## 1. Save and Quick Scan

- Save all files.
- Skim the diff for obvious issues:
  - Unexpected file rewrites
  - Unused imports
  - Large structural changes you didn’t intend

---

## 2. Run the App Locally

```bash
uv run streamlit run app.py
```

Verify:

- App launches with no stack trace
- File upload works
- Classification renders correctly
- Unknown file types fail gracefully

Stop the server with:

```
Ctrl + C
```

---

## 3. Run Linting and Formatting

```bash
uv run ruff check .
uv run black .
```

Resolve any reported issues before committing.

---

## 4. Review Changes Before Commit

```bash
git status
git diff
```

You should understand every change being committed.

---

## 5. Commit

```bash
git add -A
git commit -m "Short descriptive message"
```

One logical change per commit.

---

## 6. Push

```bash
git push
```

If using feature branches:

```bash
git checkout -b feature/description
git push -u origin feature/description
```

---

# Definition of Done (Per Increment)

Before committing:

- App runs without errors
- Feature works on at least 2 real test files
- Unknown inputs fail safely
- Diff reviewed manually
- Lint passes

---

# Adding Ruff and Black

## Install Dev Dependencies

```bash
uv add --dev ruff
uv add --dev black
```

Commit the dependency update:

```bash
git add pyproject.toml uv.lock
git commit -m "Add ruff and black dev dependencies"
git push
```

---

## Usage

Check code:

```bash
uv run ruff check .
```

Format code:

```bash
uv run black .
```

Run both before committing larger changes.

---

# Adding This File to the Repository

Create the file:

```bash
touch DEV_WORKFLOW.md
```

Paste this content into the file and save.

Then commit:

```bash
git add DEV_WORKFLOW.md
git commit -m "Add development workflow documentation"
git push
```

---

# Optional Future Upgrade

Later enhancements may include:

- Pre-commit hooks
- GitHub Actions CI checks
- Automated lint enforcement on pull requests

