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

## Branch protection ruleset

The ruleset **Protect main** is active on `main`. It applies to everyone, including the repo owner. You can view it under Settings → Rules → Rulesets.

| Rule | What it means for you |
|---|---|
| Pull request required, 1 approval | You can't push to `main`. Open a PR and get one teammate to approve it. You can't approve your own PR. |
| Dismiss stale approvals | If you push new commits after an approval, the approval is cleared and the PR needs a fresh review. |
| Branch must be up to date | If `main` changed after you branched, the PR can't merge until you click **Update branch** or merge `main` into your branch. |
| Block force pushes | History on `main` can't be rewritten. |
| Block deletion | `main` can't be deleted. |

Merge conflicts also block a PR. If two people edit the same lines, GitHub disables the **Merge** button until the conflict is resolved.

### Example: two people working in parallel

Likhit and Sam both start from the same `main`, each on their own branch (`feature/login` and `feature/api`). Both change line 10 of `app.py`.

1. Likhit's PR is approved by Sam and merged first. `main` now has Likhit's change.
2. Sam's PR shows "This branch has conflicts" and can't merge.
3. Sam brings `main` into the branch and fixes the conflict:
   ```
   git checkout feature/api
   git fetch origin
   git merge origin/main
   ```
   Git marks the conflicting lines with `<<<<<<<`, `=======` and `>>>>>>>`. Sam keeps the correct code, deletes the markers, then runs:
   ```
   git add app.py
   git commit
   git push
   ```
4. Likhit approves again, because new commits cleared the earlier approval. Sam merges.
5. Both run `git checkout main` and `git pull`, and have identical code.

### Tips

- Run `git pull` on `main` before you start a new branch.
- Merge `main` into your branch often, so conflicts stay small.
- Tell each other which files you are editing.
