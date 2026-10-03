# Upload AgriSense to GitHub from Windows

Run these steps yourself after reviewing [Day 1 verification](PROGRESS.md). The local repository uses `main`. Day 1 preparation does not create a GitHub repository, push code, or make the first commit.

## 1. Review the local repository

Open PowerShell in VS Code:

```powershell
cd C:\Zekrui\agrisense
git --version
git status
git branch --show-current
git remote -v
```

Run all Git commands at this project root. The frontend and backend belong to the same repository.

If Git reports **detected dubious ownership**, Windows created this workspace under a different owner. For this known project folder, add its exact path to Git's trusted directories, then rerun `git status`:

```powershell
git config --global --add safe.directory C:/Zekrui/agrisense
git status
```

This trusts only the named folder. If you moved the project, use its actual full path.

Check your commit identity:

```powershell
git config user.name
git config user.email
```

If either is missing, replace these example values with your name and the email address you want on commits. You may use your GitHub-provided private email address. These commands set identity for this repository only:

```powershell
git config user.name "YOUR NAME"
git config user.email "YOUR EMAIL"
```

## 2. Check exclusions and create the first commit

```powershell
git check-ignore -v backend/.env frontend/.env.local .venv/ frontend/node_modules/ frontend/.next/ .tools/
git add .
git diff --cached --stat
git diff --cached --name-only
```

Review the staged paths before committing. The actual `.env` files, dependencies, downloaded tools, datasets, and generated model files should be absent; the `.env.example` files and `frontend/package-lock.json` should be present.

If a file should not be staged, remove it from the index while leaving the local file in place with `git rm --cached -- "path/to/file"`, then correct `.gitignore`.

Commit after review:

```powershell
git commit -m "Complete Day 1: Next.js frontend and FastAPI health API"
```

## 3. Create an empty GitHub repository

Sign in to [GitHub](https://github.com), choose **New repository**, and name it `agrisense`. Choose public or private visibility. Leave initialization options for README, `.gitignore`, and license unchecked because this local project already has its own files. Copy the new repository's HTTPS URL. This follows [GitHub's existing-code upload instructions](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github).

## 4. Connect and push

Replace `YOUR_GITHUB_USERNAME` in the following URL:

```powershell
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/agrisense.git
git remote -v
git push -u origin main
```

If `origin` already exists, inspect `git remote -v` and use the intended existing remote. If it points to the wrong repository, change it deliberately with `git remote set-url origin https://github.com/YOUR_GITHUB_USERNAME/agrisense.git`.

Complete the browser sign-in if Git Credential Manager prompts. Do not paste a token into the remote URL or store it in a project file. See [GitHub authentication](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/about-authentication-to-github) if sign-in fails.

Refresh the repository page on GitHub and confirm the README and both application folders appear. Future changes use `git add .`, a new `git commit -m "Describe the change"`, and `git push`.
