# AIE-HACKATHON: Second Opinion

Three independent AI agents work on a ticket and a script decides whether they got it right.

- The **Orchestrator** talks to you, hands out the work, answers questions, runs the tests and decides pass or fail.
- The **Engineer** writes the change.
- The **Tester** writes the tests.

The Engineer and Tester never see each other's work. They run on the Meta model API, talk to the Orchestrator through [Fetch.ai uAgents](https://uagents.fetch.ai) mailboxes, and you can chat with the Orchestrator from [ASI:One](https://asi1.ai). A local dashboard shows how each run went: who asked what, what failed, and what each agent assumed.

The tickets come from the **experiment rig** in `experimentation_rig/`: a toy store database with planted data problems, and a scorer that measures how many of them the Tester caught.

## How a run works

```
  You (ASI:One chat, or the dashboard's Run button)
        |  "exp1"
        v
  Orchestrator ---- same requirement ----> Engineer      writes migrations/ queries/ src/
        |                                  Tester        writes tests/
        |  <---- questions, files -----   (no direct channel between them)
        |
        |-- answers questions from the approved contract
        |-- runs the Engineer's change and the Tester's tests on a throwaway copy of the repo and database
        |-- tests fail?  sends the Engineer only the failing test names, never test source  (up to MAX_ROUNDS)
        '-- scores the result with the rig and reports back
```

1. Each agent gets the **vague ticket** plus the repo's schema and files. By default the approved contract is *not* shown; it is released as answers to the agents' questions (see `CONTRACT_MODE`).
2. Each agent can look at the real data with **read-only SQL** (one `SELECT` at a time, a handful per turn) before it decides anything.
3. If the requirement is unclear, an agent **pushes back** with specific questions instead of guessing. The Orchestrator answers only from the contract, or says "Not specified in the approved contract."
4. Both agents list the **assumptions** they made and the reason for their change.
5. **Pass or fail comes only from pytest's exit code**, never from a model's opinion. The rig then scores the run: planted problems caught, false alarms, and whether the Engineer passes the hidden tests.

Rules the code enforces:

- The Engineer may write only under `migrations/`, `queries/` and `src/`. The Tester may write only under `tests/`. Absolute paths, `..` and anything else are dropped.
- Both agents ignore every sender except the Orchestrator, and the Orchestrator checks that a submission really comes from the role it claims.
- Feedback to the Engineer never contains test source.
- Runs never change the tickets or the rig. They work on throwaway clones.

## Quick start

Commands are for Windows PowerShell. On macOS or Linux use `source .venv/bin/activate` and `cp` instead of `.venv\Scripts\Activate.ps1` and `copy`.

You need Python 3.12 or newer (everything here was tested on 3.14, with a workaround that is already in the code), a Meta Model API key with two model IDs, and an [Agentverse](https://agentverse.ai) account for the mailboxes.

### 1. Install

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1        # if scripts are blocked: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt
```

### 2. Configure

```powershell
copy .env.example .env
```

Open `.env` and fill in at least:

| Key | Value |
|---|---|
| `MODEL_API_KEY` | your Meta Model API key |
| `ENGINEER_MODEL` | a model ID, for example `muse-wonder-1.0` |
| `TESTER_MODEL` | a model ID. Use a **different** one from the Engineer for a real second opinion |
| `META_BASE_URL` | `https://api.meta.ai/v1` (not `/v1/responses`; that gives a 404) |

Then generate each agent's seed and address. The seeds go into `.env` and are never printed:

```powershell
python setup_env.py
```

`.env` is gitignored. Never commit it.

### 3. Prepare the rig and check the model

```powershell
python -m experimentation_rig.rig reset          # fresh database and toy repo
python -m experimentation_rig.rig selfcheck exp1 # confirms the rig itself is sound (about 15 s)
python check_models.py                           # calls the Engineer and Tester models once each
```

### 4. Start everything

Open four terminals in the repo folder, activate the venv in each, and run one command per terminal:

```powershell
python engineer.py
python tester.py
python orchestrator.py
python dashboard.py
```

Each agent prints its address and an **inspector link** (`https://agentverse.ai/inspect/?uri=...`). Open each of the three links, click **Connect**, then **Mailbox**. Until you do, the log says `Agent mailbox not found`, which is expected. Startup can take up to half a minute because of the Agentverse calls.

### 5. Use it

- **Dashboard**: open <http://127.0.0.1:8050>, pick a ticket and press **Run**.
- **Chat from the terminal**: `python dev_client.py tickets`, then `python dev_client.py exp1`.
- **Chat from ASI:One**: once the Orchestrator's mailbox is connected, message it in ASI:One by its address (printed when it starts). Its profile text comes from `orchestrator_README.md`.

Chat commands:

| You say | What happens |
|---|---|
| `tickets` (or "what issues do we have?", "list the available tickets") | Lists the tickets by name |
| `exp1`, `run exp2`, `exp1 exp2` | Starts a run for each. Run the same ticket as often as you like |
| `what is exp1 about?` | Shows the ticket text |
| `task: add a function ...` | Starts a free-form task. This is the only way to start one |
| anything else | A short help reply. Nothing starts by accident |

### Offline mode (no keys, no network)

```powershell
python run_local.py                              # Engineer fails round 1, passes round 2
$env:LOCAL_SCENARIO="pushback"; python run_local.py   # adds a pushback and a contract answer
```

This runs all three agents in one process with a fake model on a fixed example task. Use `LOCAL_PORT` if port 8000 is busy.

## The dashboard

`python dashboard.py` serves <http://127.0.0.1:8050> (localhost only).

- **Left**: the tickets, by name only. A ticket has no status; you can run it any number of times.
- **Run**: queues a run. The Orchestrator picks it up within a few seconds. No chat session is needed.
- **Run chips**: one per run. Open any earlier run.
- **Agents tab**: the Orchestrator, Engineer and Tester as cards with what each is assigned, what it is doing now, and speech bubbles for questions, answers, SQL, failures and the score. Step through with Prev and Next (or the arrow keys), **Replay** the run, or follow it **Live**. Click a marker on the timeline to inspect that step: the requirement, questions and answers, the SQL and its results, how a test failed, code diffs between rounds, assumptions, and the rig's score.
- **Lineage tab**: the same run as a message-by-message sequence diagram.

## The experiment rig

`experimentation_rig/` is self-contained (see its own `README.md`, `STATUS.md` and `docs/rig-architecture.md`).

- **Tickets**: `exp1` (make `orders.amount` numeric) and `exp2` (best customers per region). `exp3` is not built.
- **Scoring**: a planted problem counts as caught when a Tester test fails on that problem's mutant but passes on the reference solution. Tests that fail on the reference are false alarms.
- **Contract**: `CONTRACT_MODE=on_pushback` (default) gives the agents only the vague ticket and releases the approved contract as answers to their questions, so you can see who pushes back and on what. `CONTRACT_MODE=upfront` gives them ticket and contract immediately, as the rig's own docs describe.

## Prompts

The editable part of each agent's instructions is a plain file you can change without touching code:

- `prompts/engineer.md`
- `prompts/tester.md`
- `prompts/clarifier.md` (how the Orchestrator answers questions)

The JSON reply format, the SQL tool and the pushback mechanism are added by `llm.py`. A short hash of each prompt is logged with every run (`task_created` in `events.jsonl`), so you can tell which prompt version produced which result. Restart the agents after editing.

## Configuration

Set these in `.env`. Only the first four are required.

| Key | Default | Meaning |
|---|---|---|
| `MODEL_API_KEY`, `ENGINEER_MODEL`, `TESTER_MODEL`, `META_BASE_URL` | | Model access (see above) |
| `CLARIFIER_MODEL` | `ENGINEER_MODEL` | Model that answers agents' questions from the contract |
| `REASONING_EFFORT` | `low` | `low` or `medium`. Meta rejects `none` |
| `CONTRACT_MODE` | `on_pushback` | `on_pushback` or `upfront` |
| `MAX_ROUNDS` | `3` | Fix attempts before the run is reported as failed |
| `TASK_TIMEOUT` | `900` | Seconds without progress before the Orchestrator gives up on a run |
| `PYTEST_TIMEOUT` | `60` | Seconds for a free-form task's tests |
| `ORCHESTRATOR_PORT`, `ENGINEER_PORT`, `TESTER_PORT` | `8000`, `8001`, `8002` | Agent ports |
| `*_SEED`, `*_ADDRESS` | | Written by `setup_env.py` |
| `DASHBOARD_PORT` | `8050` | Dashboard port |
| `WORKSPACE_DIR`, `EVENTS_FILE`, `QUEUE_DIR` | `workspace`, `events.jsonl`, `queue` | Where runs are recorded |
| `PROMPT_DIR` | `prompts` | Where the prompt files are read from |
| `REPORT_EVENTS` | `1` | Set `0` to skip Agentverse telemetry |

A full run on a rig ticket with real models takes about 5 to 15 minutes. Most of it is model time. Lower `MAX_ROUNDS` for a faster loop.

## What is where

| Path | Purpose |
|---|---|
| `orchestrator.py` | Chat, task routing, pushback answers, running tests, scoring, queue and watchdog |
| `engineer.py`, `tester.py` | The two agents. Both use `agent_core.py` for one model turn |
| `llm.py` | Meta model calls, prompt loading, SQL tool loop, offline stub |
| `rig_bridge.py` | Adapter to the experiment rig (tickets, repo context, SQL, test runner, scoring) |
| `messages.py` | The messages the agents send each other |
| `events.py` | Shared event log used by all three agents |
| `dashboard.py`, `dashboard.html` | The local dashboard |
| `prompts/` | Editable prompts |
| `setup_env.py`, `check_models.py`, `dev_client.py`, `run_local.py` | Setup, model check, terminal chat client, offline run |
| `orchestrator_README.md` | The Orchestrator's public profile text on Agentverse and ASI:One |
| `experimentation_rig/` | The toy database, tickets, hidden tests, mutants and scorer |

Each run writes:

- `events.jsonl`: every message and decision, one JSON object per line. The dashboard reads this.
- `workspace/<task_id>/`: `contract.txt`, `submissions/r<round>_<role>.json` (files, reason, assumptions, questions), `round_<n>/`, and `score.json` for rig tickets.
- `queue/`: dashboard run requests waiting for the Orchestrator.

All three are gitignored.

## Security

- Secrets live only in `.env` (gitignored). Seeds and the API key are never printed or logged. Commit `.env.example`, not `.env`.
- The dashboard binds to `127.0.0.1`. Its Run endpoint accepts only same-host JSON requests and known ticket ids.
- **Model-written code runs on your machine** with a timeout and with secrets stripped from its environment, but not in a sandbox. Run this on a machine you are comfortable with.
- Everything shown in the dashboard that came from a model is rendered as plain text.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `404` from the model check | `META_BASE_URL` must be `https://api.meta.ai/v1` |
| `Agent mailbox not found` | Open the agent's inspector link and connect its mailbox |
| Agents start slowly or hang offline | Agentverse calls at startup. Set `REPORT_EVENTS=0`, or use offline mode |
| `There is no current event loop` | Python 3.14 with uAgents 0.26. Already handled in the entry points. In a new script, call `asyncio.set_event_loop(asyncio.new_event_loop())` before creating agents |
| ASI:One message starts nothing or only shows help | Say `tickets`, then `exp1`. Free-form work needs the `task:` prefix |
| The Run button does nothing | The Orchestrator must be running. It checks `queue/` every 5 seconds |
| Scoring fails with `No module named yaml` | `pip install -r requirements.txt` |

## Known limits

- The Engineer and Tester can use the same model, so their assumptions can correlate. Give them different model IDs.
- Orchestrator state is in memory. Restarting it loses runs that are still in progress (finished runs stay in `events.jsonl`).
- Passing the Tester's tests is not the same as being right. The rig's hidden tests and score are the real measure.
- The prompts are written for the rig's repository. Free-form `task:` work uses the same prompts and is best treated as a demo.

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
