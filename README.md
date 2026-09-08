# ORDF-247: order totals wrong with stacked discount codes

This is a coding-agent RL environment built around one repository-level debugging task in a small Python pricing library. An agent is handed a repo with a broken build (a nonexistent pinned dependency) sitting in front of two independent business-logic bugs, a bug report written the way a real support escalation reads, and a spec document that's the actual source of truth. Nothing about which files are broken, or how many bugs there are, is told to the agent up front, that information lives in `task.yaml`, which the agent never sees.

This document is the engineering design document for the environment itself: why the task is shaped the way it is, how grading actually works, what I tried to break it, and where I think it's still weaker than I'd like.

## Directory layout

```
task/instruction.md          the ticket, as the agent reads it
task/task.yaml                metadata: known bug locations, scoring, what's hidden from the agent
environment/Dockerfile        container definition
environment/repo/             the buggy repo, as the agent receives it
solution/reference_solution/  a fixed copy of the repo (hidden from the agent)
tests/verifier/                the hidden test suite + grading script (hidden from the agent)
analysis/grader_attacks.md    red-team attempts against the grader, with real results
analysis/model_runs.md        real pass@k data from two models, six runs
```

## Capability mapping

This task is built to require, and to actually exercise, four distinct things, none of which is meaningfully gameable in isolation:

**Reading before writing.** The ticket deliberately doesn't say how many bugs there are or where they live. It says one test is failing, gestures at a second complaint that "might not be the same bug," and tells the agent to read `docs/PRICING_RULES.md` because the doc, not the code, is the source of truth. An agent that jumps straight to making the one failing test pass (say, by special-casing the two percentages in that specific test) will not have touched the second bug, and the second bug has no visible test pointing at it at all the only way to find it is to read the spec doc, read `engine.py`, and notice that `engine.py` computes the discountable amount as `subtotal + shipping_cost` when the doc is explicit that shipping is never discounted. That's a real comprehension check, not a keyword-matching one.

**Build/dependency debugging as a prerequisite, not a bonus.** `pytest` cannot even start against the starting repo, because `requirements-dev.txt` pins `pytest==99.0.0`, a version that has never existed on PyPI. This has to be diagnosed and fixed before the agent can get any test feedback loop running at all, which means an agent that can't do basic dependency triage is stuck before it ever reaches the interesting part of the task. I picked a fake version number rather than, say, a real but incompatible one, specifically so the failure mode is unambiguous (`pip` will say "no matching distribution," not something that could be mistaken for a network flake).

**Multi-file reasoning across non-adjacent files.** The two bugs live in `orderflow/discounts.py` and `orderflow/engine.py`, and neither one's fix depends on the other, but understanding *why* the shipping bug is a bug requires reading `orderflow/shipping.py` (correct, and explicitly documented as checking pre-discount subtotal) and `docs/PRICING_RULES.md` (which states the shipping-is-never-discounted rule in plain language) at the same time as `engine.py`. A model that fixes one bug and stops has genuinely done half the job, and the hidden suite is built so that half-done submissions land in the middle of the score range rather than either extreme.

**Preserving behavior it wasn't asked to touch.** The ticket explicitly tells the agent not to weaken existing input validation and not to edit the spec doc into agreement with whatever the code does. Both of those are real, checked constraints, see `analysis/model_runs.md` for a case where a model violated the first one by accident while doing an otherwise-correct rewrite.

## Environment logic: stochasticity

There isn't much stochasticity to handle here, and that's deliberate rather than an oversight. The pricing logic itself is pure, no wall-clock reads, no random numbers, no network calls, no filesystem state beyond the source files themselves. Decimal arithmetic is used throughout (`decimal.Decimal` with explicit `ROUND_HALF_UP` quantization to the cent) specifically so that "same inputs, same output" holds exactly, with no floating-point drift between a run on my machine and a run anywhere else.

The one place I did introduce controlled randomness is on the grading side, not the environment side: the hidden test suite generates its `order_id` values from `uuid.uuid4().hex[:8]` plus a running counter, rather than using fixed literal strings. That's not simulating real-world noise, it's there to stop a submission from hardcoding answers keyed to specific, guessable test inputs (see `analysis/grader_attacks.md`, attack 1). Every hidden test's *expected values* are still fully deterministic; only the identifier used to construct the order varies from run to run, and nothing about the pricing math depends on what that identifier is, so re-running the hidden suite twice against the same submission always produces the same pass/fail pattern even though the literal order IDs differ each time.

Given all that, an agent's environment session is fully reproducible: same starting repo, same Docker base image pinned to a specific tag (`python:3.11.9-slim-bookworm`), same dependency versions for the runtime package (`requirements.txt` is empty, this package has zero runtime dependencies by design, which keeps the "does it install" question narrowly about the dev/test tooling pin that's actually broken).

## Oracle strategy: behavior, not text

The grading script (`tests/verifier/grade.py`) never inspects a submission's source code directly, and never greps output. It checks behavior:

1. Copy the submission to a scratch directory.
2. Overwrite the submission's `tests/test_pricing.py` and `tests/verifier/test_hidden_pricing.py` with pristine copies kept outside the submission tree entirely, so nothing the agent did to either file (edit it, delete it, replace it with a fake) has any effect.
3. Install the package itself from the scratch copy (`pip install -e .`), so a submission that legitimately touched `pyproject.toml` is graded fairly rather than penalized for it.
4. Install dev/test dependencies from the submission's own `requirements-dev.txt`. If this fails, grading stops immediately and the submission fails outright, this is the mechanism that actually enforces "the broken pin has to be fixed," rather than that requirement being a sentence in the ticket that nothing checks.
5. Run the regression suite and the hidden suite as two separate pytest invocations, each producing its own JUnit XML report, each under a hard subprocess timeout.
6. Parse the JUnit XML (not stdout) into a pass/fail map per test. Verdict is strict: every test in both files has to be green for a PASS. A separate score (fraction of hidden tests passing) is recorded alongside the verdict, for analysis, but is never used to grant partial credit toward the pass/fail call itself.

The distinction I care about most here is "behavior vs. output." I'm not diffing the submission against the reference solution's source code, and I'm not checking whether specific lines changed, a submission could restructure `discounts.py` completely differently from the reference fix (different variable names, different control flow, even a different but equivalent algorithm) and still pass, as long as the actual priced totals it produces match the spec across the full hidden scenario set. Conversely, a submission that looks like it made "the right kind of change" by eyeballing a diff, but gets an edge case wrong (the free-shipping threshold check, the blended tax rate on mixed-category carts, the floor-at-zero behavior for an oversized flat discount), fails, because the hidden suite actually exercises those scenarios and checks the resulting numbers against values I derived independently from `docs/PRICING_RULES.md` using the same Decimal arithmetic the library itself uses.

The hidden suite is about 2.7x the size of the visible one (16 hidden tests against 6 visible ones) and covers: duplicated regression coverage (so a submission can't pass the hidden suite while failing the visible one through some quirk of how they're invoked separately), each bug in isolation, both bugs combined in a single realistic cart, the exact worked example from the spec doc, several category/tax-rate combinations, free-shipping boundary conditions on both sides of the threshold for both shipping regions, and this is the one that actually caught a real model failure during testing, see `analysis/model_runs.md` a test that bypasses the dataclass's own constructor validation to check that `apply_discounts()` has its own defense against a malformed discount reaching it, which is existing behavior in the starting repo that a naive rewrite can silently drop.

## Adversarial analysis (summary)

Full writeup with real scores is in `analysis/grader_attacks.md`. Four attacks were actually run against real (deliberately broken) submissions, not just described:

- **Hardcoding answers to the visible tests**  fails at 0.375 because the hidden suite's randomized order IDs never match anything in a hardcoded lookup table.
- **Deleting or fabricating the test files** fails identically to whatever the underlying (unfixed) submission would score anyway, because the harness stamps pristine test files over the submission's copy before installing or running anything.
- **Fixing both real bugs but stripping input validation**  scores a deceptively high 0.875 (14/16), which is exactly why the pass condition is "100% of both suites," not a threshold; the two tests it fails are there specifically to catch this.
- **Fixing both real bugs but leaving an infinite loop reachable in the pricing path**  fails at 0.0 in about 96 seconds of wall-clock time, because every subprocess call in the grader runs under a hard timeout that converts a hang into a clean failure rather than an indefinite stall.

## Honest limitations

Two things I want to be upfront about rather than let a reader discover on their own.

**I could not run an end-to-end `docker build` in the sandbox I built this in.** The Docker daemon itself starts fine, but every container registry I tried (`docker.io`, `mcr.microsoft.com`) returned 403 through this sandbox's network egress proxy, and there's no local image cache or registry mirror available to fall back on. I did not paper over this: the Dockerfile is written and pinned the way I'd want it in production (exact base image tag, pinned pip/setuptools/wheel, layered `COPY` so dependency installation isn't invalidated by unrelated code changes, an explicit comment on why `requirements-dev.txt` is deliberately *not* installed at image-build time), but I have not personally watched it build successfully end-to-end. What I did instead was verify every piece of actual logic  the buggy repo, the reference fix, the grading script, all four adversarial attacks, and all six blind model runs  inside a plain Python 3.11 virtual environment on the same base OS family the image targets (Debian bookworm), which exercises the exact same dependency resolution and test execution the container would run, just without the container boundary itself. If you have real registry access, the build should be a single `docker build -t ordf247 environment/` from this directory, and I'd genuinely want to know if it doesn't work, because that would mean something in the Dockerfile itself is wrong rather than just untested by me.

**Isolation between the agent and the hidden materials in my own test runs was directory-based, not container-based**, for the same registry-access reason above. When I ran the six blind model evaluations documented in `analysis/model_runs.md`, I physically moved `solution/reference_solution/` and `tests/verifier/` out of the tree to a separate path before handing any model a working directory, and instructed each run not to search outside its assigned directory. That's a reasonable stand-in for what a real container boundary gives you for free, but it's not the same guarantee a sufficiently curious or capable agent with unrestricted filesystem access could in principle go looking for a path it was told not to look at. In an actual deployment of this environment, the container boundary in the Dockerfile (no mount of `solution/` or `tests/verifier/` into the agent's container at all) is what should be doing this job, not an instruction in a prompt.

Neither limitation affects the correctness of the grading logic itself, which I did verify directly and exhaustively (four adversarial attacks, two mutation tests against the reference solution with individual fixes reverted, and six real model runs, all with saved JSON output) they affect how confident I can be that this specific container definition builds cleanly on a host with real network access, and how strong the isolation guarantee is in a from-scratch run versus the directory-separation approach I used here.
