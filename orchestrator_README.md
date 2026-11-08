# Second Opinion

I run two independent AI agents on a ticket and tell you whether their work holds up.

- The **Engineer** writes the change.
- The **Tester** writes the tests, without seeing the Engineer's work.
- If a ticket is vague, each of them asks me specific questions before guessing. I answer only from the approved contract.
- Pass or fail comes from running the tests, never from an AI's opinion. I then score the run on how many planted data problems the tests caught.

## What to say

- `tickets` lists the tickets I can work on.
- `exp1` (or `run exp2`) starts a run. You can run the same ticket as often as you like.
- `what is exp1 about?` shows the ticket text.
- `task: <describe a task>` starts a free-form task. Nothing else starts work.

## What you get back

Short progress updates (who asked what, tests running, retries) and a final PASS or FAIL with the score. A local dashboard shows each run step by step.

## Limits

- A run on a ticket takes roughly 5 to 15 minutes.
- Free-form tasks are a demo; the tickets are what I am built for.
- Generated files stay on the machine that runs me.
