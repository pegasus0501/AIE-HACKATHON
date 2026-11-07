# AIE-HACKATHON

## Team workflow

`main` is protected. Nobody pushes to it directly. Every change goes through a pull request.

1. Update your local `main`:
   ```
   git checkout main
   git pull
   ```
2. Create a branch for your feature:
   ```
   git checkout -b feature/short-name
   ```
3. Commit and push the branch:
   ```
   git add <files>
   git commit -m "Describe the change"
   git push -u origin feature/short-name
   ```
4. Open a pull request into `main` on GitHub.
5. If GitHub says the branch is out of date, click **Update branch**, or run:
   ```
   git fetch origin
   git merge origin/main
   ```
   Resolve any conflicts, commit, and push again.
6. A teammate approves the PR, then you merge it.
