# Publishing Dhruv's integrated SilverFile branch

Your current silverfile-app folder is not a Git repository. Do not run git init and force-push it over the team repository. Clone the existing integration branch into a separate folder, create a new branch, and copy the integrated files there. Your working local app and its saved cases stay in place.

These steps prepare a new branch; they do not merge into main. No push has been performed by the assistant.

## 1. Put the sharing files into the local app

From this sharing package, copy these files into silverfile-app:

- README_TEAM.md
- requirements-team.txt
- .gitignore (replace the existing file with this expanded version)
- .env.example (replace the old example; this one contains no key)
- PUBLISH_STEPS.md (optional to include in the repository)

The handoff note previously supplied should be at docs/ORCHESTRATION_DASHBOARD_HANDOFF.md. Preserve existing docs/PDF_EXPORT.md and all original contributor files.

Finder hides dotfiles; press Command+Shift+Period to show .gitignore and .env.example. Open the files in VS Code if easier.

Add these lines at the very beginning of the existing README.md, keeping the contributor history below them:

```markdown
# SilverFile integrated application

Start here: [Teammate setup and demo guide](README_TEAM.md).

This branch includes the integrated workflow, staff dashboard, and reviewed 1040-SR draft export. The component documentation below records earlier work; use the teammate guide for the current entry points.

---
```

## 2. Clone the existing team integration branch

In a new terminal, run:

```sh
cd "/Users/dhruvrawat/Desktop/CLASS/Sem 3/ENMGT 5405 AI/Assignment 7"
git clone --branch yong/integration https://github.com/DhruvRawat418/Assignment7_taxsystem.git silverfile-publish
cd silverfile-publish
git switch -c dhruv/silverfile-integrated
```

The base branch and repository URL come from the current project README. If the branch has been renamed or the destination directory already exists, stop and inspect the situation rather than deleting a folder or force-pushing. For a private repo, sign in through GitHub/VS Code or your normal Git credential manager; do not embed a token in the URL.

## 3. Copy your integrated app into the new checkout

Still inside silverfile-publish, run this complete command. It copies source and synthetic fixtures, while excluding local environments, credentials, caches and saved cases:

```sh
rsync -av \
  --exclude='.git/' \
  --exclude='.venv*/' \
  --exclude='venv/' \
  --exclude='__pycache__/' \
  --exclude='.pytest_cache/' \
  --exclude='.DS_Store' \
  --exclude='.superpowers/' \
  --include='.env.example' \
  --exclude='.env' \
  --exclude='.env.*' \
  --exclude='.streamlit/secrets.toml' \
  --exclude='*.db' \
  --exclude='*.db-wal' \
  --exclude='*.db-shm' \
  --exclude='*.sqlite*' \
  --exclude='outputs/' \
  --exclude='*-1040-SR-draft.pdf' \
  --exclude='*-audit-record.json' \
  "../silverfile-app/" ./
```

No --delete flag is used; this does not erase files from the existing checkout. Review unexpected retained files before committing.

## 4. Check what will be published

```sh
git status --short
git diff --stat
git diff --check
git ls-files -- '*.db' '*.db-wal' '*.db-shm' '.env' '.streamlit/secrets.toml'
```

The last command should print nothing. Ignore rules do not untrack a file that was committed previously. If it prints anything, stop and remove it from tracking before proceeding. If a real key was ever committed, removing the current file is insufficient: revoke the key and address the repository history with the team.

Confirm these are present: dashboard.py, pdf_export.py, requirements-team.txt, requirements-pdf.txt, demo/retry_review.py, demo/resolve_scope.py, tests/integration/test_pdf_export.py, assets/f1040s--2025.pdf, and demo/w2_clean.jpg. Review changes in VS Code's Source Control panel. Do not include personal tax documents or private keys.

Run tests from the new checkout using your existing known-working interpreter:

```sh
"../silverfile-app/.venv/bin/python" -m pytest tests -q
```

This verifies the copied code with the existing environment. It does not verify fresh dependency installation; a teammate should also follow README_TEAM.md in a new environment.

## 5. Commit and push the new branch

After reviewing the files and passing tests:

```sh
git add .
git diff --cached --stat
git diff --cached --name-only
```

Check the staged list once more: no API keys, .env files, .venv folders, or SQLite databases. Then:

```sh
git commit -m "Integrate SilverFile workflow, staff dashboard, and draft PDF export"
git push -u origin dhruv/silverfile-integrated
```

Do not add --force. If Git asks for identity, use your own Git name/email; if it asks for authentication, use GitHub's normal sign-in flow rather than posting a credential in chat.

## 6. Share the branch

After the push succeeds, share:

https://github.com/DhruvRawat418/Assignment7_taxsystem/tree/dhruv/silverfile-integrated

Ask teammates to begin with README_TEAM.md, use Python 3.12, create their own virtual environment, and use their own API key. Existing local cases are intentionally not included; the guide provides exact answers to recreate clean, correction, and stop cases.

You can open a pull request into the team's agreed integration/main branch when everyone has reviewed the result. Preserve original contributor branches and attribution. Do not merge over teammates' work without coordinating the target branch.

## After teammates start contributing

Use the Git checkout for future shared work so changes are captured by commits. Keep the original silverfile-app folder as your existing demo environment until you deliberately migrate its local saved cases. Avoid editing two copies without tracking which one you will publish.
