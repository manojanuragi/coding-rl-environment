# Model runs

I ran this task against two models, three attempts each, with each attempt getting a completely fresh, isolated copy of the buggy repo and nothing else the ticket text in `task/instruction.md`, the repo, and shell access inside that one directory. No attempt could see the reference solution or the hidden test suite (both were physically moved out of the working tree before any run started), and no attempt could see any other attempt's work. Every result below is from actually running `tests/verifier/grade.py` against what the model left behind, not from trusting what the model said about its own work in its final summary  which turns out to matter a lot, for reasons that show up directly in the data.

Models used: a smaller/faster model ("haiku") and a larger model ("sonnet") from the same family, run through the same agent harness with the same tools and the same instructions. I'm not naming exact model versions here because the point of this section is the *methodology*  what the oracle catches that self-report doesn't  rather than a vendor comparison, but the two models are at a meaningfully different capability tier from each other.

## Results

| Run | Verdict | Score (hidden suite) | Fixed both business-logic bugs? | Fixed the dependency pin? |
|-|-|-|-|-|
| haiku, attempt 1 | FAIL | 0.0 | yes | **no** |
| haiku, attempt 2 | FAIL | 0.0 | yes | **no** |
| haiku, attempt 3 | PASS | 1.0 | yes | yes |
| sonnet, attempt 1 | PASS | 1.0 | yes | yes |
| sonnet, attempt 2 | FAIL | 0.9375 | yes (see below) | yes |
| sonnet, attempt 3 | PASS | 1.0 | yes | yes |

"Score" is the hidden-suite pass fraction `grade.py` reports for analysis; the verdict used for pass@k is the strict one (regression suite AND hidden suite both 100%).

## pass@k

Treating each attempt as an independent trial:

- **haiku:** pass@1 = 1/3 (0.33), pass@3 = 1/1 (at least one of the three attempts passed, so pass@3 = 1.0)
- **sonnet:** pass@1 = 2/3 (0.67), pass@3 = 1.0

Both models get to 1.0 by the third attempt, which on its own would suggest the task is "easy with enough tries" for both. That framing turns out to be wrong, and the reason is the most interesting thing in this whole run: **the two haiku failures and the one sonnet failure are not the same kind of failure at all**, and pass@k alone doesn't distinguish them.

## Stump percentage: 0%, and why that number is misleading on its own

If "stumped" means the model didn't meaningfully engage  gave up, produced no diff, asked to be let off the task, or made changes so far off-base they don't touch either real bug  then the stump rate here is 0% for both models across all six attempts. Every single run correctly diagnosed all three problems described or implied by the ticket (the broken pin, the discount-compounding bug, the shipping-discount bug) and produced a plausible, on-topic fix for all three. Sonnet's attempts additionally connected the "customer shipping to Canada" detail in the ticket to the shipping bug explicitly in their reasoning; haiku's attempts fixed the same bug without narrating that connection as clearly, but fixed it all the same.

So a 0% stump rate says both models "understood the task." It says nothing about whether they finished it correctly, and in this run, that gap is exactly where the two failure modes below live.

## Failure mode 1 (haiku, attempts 1 and 2): confidently wrong about the install step

Both failing haiku attempts fixed `discounts.py` and `engine.py` correctly  I checked the actual diffs, not just the grader output, and the business logic in both is functionally identical to the reference fix (separate FLAT/PERCENT handling, best-percent-only, discount applied to subtotal alone, not to subtotal-plus-shipping). Both attempts also **left `requirements-dev.txt` completely untouched**  still pinned to `pytest==99.0.0`, the exact broken pin from the starting state. And both attempts' final summaries reported running the test suite and getting six passes.

That's not a lie so much as a stale premise: whatever pytest each of those sessions actually invoked was not installed from a clean `requirements-dev.txt` in the way `grade.py` insists on  the harness re-installs dev dependencies from the submission's own requirements file into a scratch copy specifically so a run can't coast on a preexisting environment. Something in those two sessions let `pytest` run anyway, the six visible tests happen to all be satisfiable by the (correct) business-logic fix alone, and the model reported that as done without ever confirming the actual definition-of-done item at the top of the ticket ("pytest runs cleanly from the repo root (right now it can't even start)"). Under the real oracle, `pip install -r requirements-dev.txt` fails immediately and grading stops there  both hidden and regression suites report as empty, verdict FAIL, score 0.0, full stop, regardless of how correct the untested logic underneath happens to be.

This is, as far as I can tell, exactly the scenario the task was designed to catch: a model that solves the hard, interesting part of the problem and skips the boring gatekeeping step, then self-reports success because its own sandbox happened to let it get away with skipping that step. A grader that only looked at whether the two business-logic bugs got fixed  by diffing source files, say, instead of actually running the install-then-test pipeline from scratch  would have scored both of these as full passes. The oracle here doesn't do that; it re-derives the environment from the submission's own dependency manifest every time, so a model that never actually satisfies "the suite installs" can't get credit for having satisfied everything downstream of it.

## Failure mode 2 (sonnet, attempt 2): a validation regression the instructions explicitly warned against

This one is more subtle and, I think, more instructive. Sonnet's second attempt fixed both real pricing bugs correctly and passed 15 of 16 hidden tests plus all 6 regression tests  a 0.9375 score, the highest of any failing attempt across either model. The one hidden test it failed was `test_unknown_discount_kind_still_rejected`, which constructs a `Discount` object with an invalid `kind` value (bypassing the dataclass's own `__post_init__` validation the way a deserialization bug upstream plausibly could) and asserts that `apply_discounts()` itself still raises `ValueError` rather than silently ignoring the bad entry.

The original buggy `discounts.py` has exactly this guard  an `else: raise ValueError(...)` for any discount kind that's neither `PERCENT` nor `FLAT`. When sonnet's attempt 2 rewrote `apply_discounts()` to separate FLAT and PERCENT handling (correctly, for the actual bug), it restructured the function into "sum the FLATs, find the best PERCENT" and, in doing so, dropped the `else` branch entirely  an unknown-kind discount is now just silently skipped instead of raising. I compared this against the two attempts that passed (sonnet attempts 1 and 3, and haiku attempt 3): all three of those independently kept an explicit `else: raise ValueError(...)` in their rewritten version of the same function, even though nothing in the visible test suite or the spec doc calls that guard out directly  it's only present as existing behavior in the code the model started from, and the ticket's "don't weaken or remove existing validation" line is the only thing telling the model it needs to survive a rewrite.

This is a real, unprompted regression, not a contrived cheat  I didn't ask sonnet to remove this guard, and I doubt the model was even aware it had, since nothing else in its diff or reasoning suggests it was deliberately narrowing scope. It's the kind of thing that happens when a correct rewrite of a function's main logic incidentally drops a side responsibility that function also had. A text-diff-based check or a grader that only ran the visible suite would have missed this cleanly (the visible suite never touches unknown discount kinds at all), and a grader using a score threshold instead of a strict pass condition would have called 0.9375 a clear win. Under the strict oracle it's correctly a FAIL, because the ticket's definition of done is explicit that existing validation has to survive, and the hidden suite has a test built specifically to check that a rewrite doesn't drop it via exactly this kind of restructuring.

## Other real differences worth noting

Every attempt that got past the pin picked a different valid pytest/pytest-cov version pair to replace the broken one with (`7.4.3`/`4.1.0`, `8.3.3`/`5.0.0`, `8.3.5`/`5.0.0`), which is expected and fine  the grader never checks the specific version chosen, only that installing from the submission's own file actually succeeds and that the suite runs under whatever got installed.

Sonnet's reasoning, visible in its final summaries, consistently drew an explicit line from the ticket's "customer shipping to Canada" detail to the shipping-discount bug before touching any code; haiku's summaries described the same fix without narrating that link as explicitly, even though the resulting code change was the same. That's a difference in how the two models explain themselves, not a difference in what they shipped  it didn't correlate with pass/fail here (haiku's one clean pass fixed the shipping bug just as completely as sonnet's clean passes did), which is itself worth noting: better narration is not evidence of a better fix, and I'd be cautious about any evaluation setup that scored explanation quality as a proxy for correctness instead of just running the oracle.

## What this run actually demonstrates

Three passes and three fails across six attempts, on a task where every attempt "understood" the ticket, is not a story about task difficulty  it's a story about the gap between an agent's own confidence and what happened in a clean, from-scratch environment. Two of the three failures here would have been scored as full passes by any grader that trusted the model's self-report, ran only the tests the model chose to run, or used a passing threshold instead of a strict all-tests condition. The oracle caught both because it doesn't ask the submission whether it's done; it rebuilds the environment from the submission's own files and checks.
