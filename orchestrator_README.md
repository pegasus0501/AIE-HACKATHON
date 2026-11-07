# Second Opinion: two independent AI engineers, one verdict

Give me a small coding task in plain English. I hand the same task to two separate agents who never see each other's work:

- **Engineer** writes the implementation.
- **Tester** writes skeptical pytest tests from the task description alone.

I run the tests and report the result. **Pass or fail comes only from pytest, never from an AI's opinion.** If the tests fail, the Engineer gets the failing test names and assertion messages (never the test code) and tries again, up to 3 rounds.

## What to ask
Small, self-contained Python tasks, for example:

- "Add a function `add(a, b)` in `src/calc.py` that returns the sum of a and b."
- "Write `slugify(text)` in `src/text.py` that lowercases and joins words with hyphens."
- "Add a function that returns the n-th Fibonacci number, rejecting negative n."

## What you get back
Short progress updates (engineer done, tester done, running tests, round 2...) and a final **PASS** or an honest **FAIL** with the last failing tests.

## Limits
- One task per message; Python only.
- Best for single functions or small modules, not whole projects.
- Generated files are stored on the host that runs me.
