# AGENTS.md

Guidance for coding agents working in this repository.

## What this repo is

The `LLSP` (Long Lived Script Processors) repository is a distributed service for executing Python
(including Mantid) scripts asynchronously via a RESTful API, decoupling submission from execution
with RabbitMQ and Celery (see `README.md`):

1. **`LLSP-API` (`LLSP-API/`)**: A FastAPI web service that accepts Python scripts via
   `POST /execute` (protected by `Authorization: Bearer <LLSP_API_KEY>`), enqueues execution tasks to
   Celery (`celery_app.exec_script`), exposes task status/output queries via `GET /status/{task_id}`,
   and provides `/healthz` and `/ready` probes (where `/ready` verifies `LLSP_API_KEY` is set).
2. **`LLSP-Worker` (`LLSP-Worker/`)**: A Celery worker built `FROM ghcr.io/fiaisis/mantid:<VERSION>`
   (with `ENTRYPOINT []` reset and `--concurrency=1`) that consumes tasks from RabbitMQ
   (`amqp://<RABBITMQ_USER>:<RABBITMQ_PASS>@<CELERY_BROKER_HOST>/llspvhost`), runs each script via
   `subprocess.run([sys.executable, "-c", script])` inside a `TemporaryDirectory`, and returns
   `{"exit_code": ..., "stdout": ..., "stderr": ...}` over the Celery result backend (`rpc://`).

*(Note: `README.md`'s `curl` examples omit the `Authorization: Bearer <LLSP_API_KEY>` header, which
is now required on both `POST /execute` and `GET /status/{task_id}`, and `README.md` uses
`docker-compose` with a hyphen whereas CI uses `docker compose`.)*

## Position in the FIA service

### Overarching FIA architecture

FIA is a multi-repository system (all checked out as siblings under the same parent workspace
directory) that automatically reduces instrument data, and also lets users browse, plot, and rerun
that data interactively:

```text
[ISIS Instrument Archive (/archive, /imat) & lastrun.txt]
        │
        ▼
  file-watcher (Kopf Operator + Per-Instrument Watcher Pods)
        │  publishes file path to RabbitMQ: `watched-files`
        ▼
  run-detection ◄──── fetches instrument rules (`GET /instrument/{inst}/specification`) ────► FIA-API
        │  ingests .nxs metadata, verifies rules, publishes JobRequest JSON
        │  to RabbitMQ: `scheduled-jobs` (or retries via `failed-watched-files`)
        ▼
  jobcontroller (job_creator) ◄──── requests PreScript (`GET /script/{inst}`) & posts Job ──► FIA-API ◄──► autoreduction-scripts
        │  spawns Kubernetes Job in cluster:
        ├──► Main container: runners (`ghcr.io/fiaisis/mantid` or `mantid-imaging`) -> writes reduced data to `/ceph`
        └──► Sidecar container: jobcontroller (job_watcher) -> updates job status/outputs in FIA-API (`PATCH /job/{id}`)

[Interactive / Web & Live Data Paths]
  scigateway (Host App) ──► frontend (FIA React Plugin)
                                ├──► fia-auth (UOWS login, JWT verify/refresh, `/experiments` RB lookup)
                                ├──► FIA-API (runs, jobs, scripts, specifications, reruns -> `watched-files` / `scheduled-jobs`)
                                └──► plotting-service (h5grove NeXus/HDF5 & IMAT image serving from `/ceph` & `/imat`)

  Kafka (`<INST>_events`, `<INST>_sampleEnv`, `<INST>_runInfo`)
        └──► live-data (Live Data Operator + Mantid Live Data Processor fetching `/live-data/{inst}/script` from FIA-API)

  LLSP (THIS REPO) (Long Lived Script Processors: `LLSP-API` + RabbitMQ + Celery `LLSP-Worker` built on `ghcr.io/fiaisis/mantid`)

[Infrastructure & Deployment]
  k8s (Terraform + Ansible for OpenStack clusters, Redpanda, local Minikube)
  gitops (ArgoCD App-of-Apps & Kustomize `base`/`envs`/`variants` manifests for all FIA services)
```

### This repository's location (upstream, downstream & siblings)

- **Role**: Provides warm, long-lived Mantid-enabled worker processes (`LLSP-Worker`) behind a fast
  HTTP task API (`LLSP-API`) so short or interactive Python/Mantid scripts can execute without cold
  per-job Kubernetes Pod/PV creation overhead.
- **Upstream inputs**:
  - HTTP callers submitting `POST /execute` and polling `GET /status/{task_id}` with
    `Authorization: Bearer <LLSP_API_KEY>`.
  - `runners` (`../runners`) — `.github/workflows/build-and-push.yml` in `fiaisis/runners`
    automatically updates `FROM ghcr.io/fiaisis/mantid:<VERSION>` in `LLSP-Worker/Dockerfile` and
    pushes a `[CD] Update base image for LLSP to ...` commit whenever a new Mantid runner release is
    built.
- **Downstream outputs**:
  - RabbitMQ (`llspvhost`) — Celery broker (`amqp://`) and `rpc://` result backend connecting
    `LLSP-API` and `LLSP-Worker`.
  - `gitops` (`../gitops`) — `.github/workflows/build-push.yml` builds and pushes both
    `ghcr.io/fiaisis/llsp-worker:latest` and `ghcr.io/fiaisis/llsp-api:latest` on every push to
    `main`, then automatically updates the image digests in
    `./components/llsp-worker/envs/staging/llsp-worker.yml` and
    `./components/llsp-api/envs/staging/llsp-api.yml`.
- **Sibling repositories to check when changing contracts**: `../runners` (updates
  `LLSP-Worker/Dockerfile`'s `FROM` line) and `../gitops` (`components/llsp-api/` and
  `components/llsp-worker/` manifests and secrets).

### Core technologies
- **Python**: version/minimum is defined by `requires-python` in `LLSP-API/pyproject.toml` and
  `LLSP-Worker/pyproject.toml` — do not hardcode a version here; check those files and
  `.github/workflows/` before creating an environment.
- **FastAPI**: Web framework for `LLSP-API`.
- **Celery** (`celery[amqp]`): Distributed task queue client (`LLSP-API`) and worker (`LLSP-Worker`)
  backed by RabbitMQ.
- **Mantid**: Pre-installed in the `ghcr.io/fiaisis/mantid` base image used by
  `LLSP-Worker/Dockerfile`.
- **pytest** (+ `pytest-cov`, `pytest-random-order`, `pytest-asyncio`, `httpx`, `requests`): Unit
  and Docker Compose E2E test suites.
- **ruff**: Linting and formatting (shared config in root `pyproject.toml`, `line-length = 120`).
- **mypy**: Static type checking (`mypy --strict LLSP-API LLSP-Worker --exclude LLSP-Worker/build`).
- **Docker & Docker Compose**: Service Dockerfiles (`LLSP-API/Dockerfile`,
  `LLSP-Worker/Dockerfile`, `tests/Dockerfile`) and compose stacks (`docker-compose.yml`,
  `docker-compose.test.yml`).

---

## Repository structure

```
LLSP-API/                    FastAPI service subproject (`llsp-api`) — routes (`/execute`,
                              `/status/{task_id}`, `/healthz`, `/ready`), bearer API-key auth,
                              Pydantic request/response models, Celery state mapping utilities,
                              `Dockerfile`, and `pyproject.toml`
LLSP-Worker/                 Celery worker subproject (`llsp-worker`) — `celery_app` task definition
                              (`exec_script` running `python -c` in a temporary directory), unit
                              tests (`LLSP-Worker/tests/`), `Dockerfile` (built on
                              `ghcr.io/fiaisis/mantid`), and `pyproject.toml`
tests/                       Root test directory — API unit tests (`tests/test_utils.py`), E2E test
                              suite (`tests/e2e/`) and `tests/Dockerfile`
docker-compose.yml,          Compose stacks spinning up RabbitMQ, `api`, `worker`, and `e2e-tests`
docker-compose.test.yml
.github/workflows/           CI/CD workflows: test.yml, lint.yml, build-push.yml
pyproject.toml               Root configuration file hosting the shared `[tool.ruff]` settings for
                              the entire repository
```

---

## Three `pyproject.toml` files — read these first

This repository splits configuration across three `pyproject.toml` files:
1. **Root `pyproject.toml`**: Contains **only** the shared `[tool.ruff]` and `[tool.ruff.lint]`
   configuration (`line-length = 120`, docstring `D` rules, `PTH`, `TCH`, `S`, `B`, `PL`, etc.).
2. **`LLSP-API/pyproject.toml`**: Package metadata and pinned (`==`) dependencies/extras
   (`formatting`, `test`, `all`) for `llsp-api`.
3. **`LLSP-Worker/pyproject.toml`**: Package metadata and pinned (`==`) dependencies/extras
   (`formatting`, `test`, `all`) for `llsp-worker`.

Keep dependencies pinned with `==`, and when updating shared dev tools (`ruff`, `mypy`, `pytest`,
`celery`), update both `LLSP-API/pyproject.toml` and `LLSP-Worker/pyproject.toml` together.

---

## Configuration (environment variables)

### `LLSP-API`
| Variable | Default | Description |
| :--- | :--- | :--- |
| `LLSP_API_KEY` | *(required — `/ready` exits if unset)* | Bearer token required on `POST /execute` and `GET /status/{task_id}` |
| `CELERY_BROKER_URL` | `amqp://user:pass@rabbitmq:5672/vhost` | Full AMQP broker URL for Celery |
| `CELERY_RESULT_BACKEND` | `rpc://` | Celery result backend URL |
| `EXEC_TASK_NAME` | `celery_app.exec_script` | Celery task name dispatched by `POST /execute` |

### `LLSP-Worker`
| Variable | Default | Description |
| :--- | :--- | :--- |
| `CELERY_BROKER_HOST` | `None` | RabbitMQ hostname (connects to vhost `llspvhost`) |
| `RABBITMQ_USER` | `foo` | RabbitMQ username |
| `RABBITMQ_PASS` | `bar` | RabbitMQ password |
| `CELERY_RESULT_BACKEND` | `rpc://` | Celery result backend URL |

---

## Environment & running commands

Do not assume any particular machine already has a conda env, kubectl context, or virtualenv set up
— check what is available first. Prefer `conda` when available (`command -v conda` on Linux/macOS or
`where conda` on Windows); fall back to a Python `venv` only if conda is not installed.

1. Check existing conda environments:
   ```shell
   conda env list
   ```
   If a matching env exists (e.g. `llsp`), use it with `conda run -n <env-name> <command>` or
   `conda activate <env-name>`.
2. If no suitable conda env exists but `conda` is installed, create one using the Python version
   from `pyproject.toml` / `.github/workflows/` and install both subprojects:
   ```shell
   conda create -n llsp python=<version-from-pyproject.toml-or-CI> -y
   conda run -n llsp pip install "./LLSP-API[all]" "./LLSP-Worker[all]"
   ```
3. Only if `conda` is not installed, fall back to a virtualenv:
   ```shell
   python3 -m venv .venv        # Linux/macOS (use `python` on Windows)
   . .venv/bin/activate         # POSIX shell (.venv\Scripts\Activate.ps1 on PowerShell)
   pip install "./LLSP-API[all]" "./LLSP-Worker[all]"
   ```

### Running tests, linting & Docker Compose
- **Unit tests, linting & type checking (from repo root, matching `.github/workflows/test.yml` and
  `lint.yml`)**:
  ```shell
  conda run -n <env-name> pytest tests/test_utils.py
  conda run -n <env-name> pytest ./LLSP-Worker/tests
  conda run -n <env-name> ruff check .
  conda run -n <env-name> ruff format --check .
  conda run -n <env-name> mypy --strict LLSP-API LLSP-Worker --exclude LLSP-Worker/build
  ```
- **E2E tests via Docker Compose** (on demand or when changing container/queue wiring):
  ```shell
  docker compose -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from e2e-tests
  ```

## Kubernetes commands

Available kubectl contexts vary per machine/operator — always run `kubectl config get-contexts`
first before targeting a cluster. Never rely on the current context; always pass `--context`
explicitly at the **end** of the command:

```shell
kubectl get pods -n fia --context <context-name>
kubectl logs deploy/llsp-api -n fia --context <context-name>
kubectl logs deploy/llsp-worker -n fia --context <context-name>
```

Double- and triple-check the context name before running anything against a production-like cluster.

## Managing issues

This repo has no local `.github/ISSUE_TEMPLATE/`; GitHub serves the org-wide default template from
`fiaisis/.github` instead. Always use it rather than inventing an ad hoc issue format:

```shell
gh issue create --template Issue
```

Check `gh issue list` / `gh issue view <number>` first to avoid duplicates.

## Branch naming

Branches use `snake_case` descriptions of the work being done. Do not use category prefixes like
`feature/` or `fix/`.

- **Format**: `description_of_work` (e.g. `add_api_key_auth`, `include_mantid_in_llsp_worker`).

## Commit messages

`main`'s history (`git log --oneline main`) is **squash merges** for PRs (`<PR title> (#<PR
number>)`, e.g. `Add api key auth (#13)`), alongside automated `[CD] Update base image for LLSP to
ghcr.io/fiaisis/mantid:<VERSION>` commits pushed by `fiaisis/runners`. This has two practical
consequences:

- **The PR title is what actually survives into permanent history.** Individual commits on a working
  branch are squashed on merge, so getting the PR title right (see "Pull request process" below)
  matters more than crafting a commit-by-commit history.
- **Individual commit messages still matter for review and for the squash commit body.** By default,
  GitHub's squash merge concatenates every commit subject on the branch into the squashed commit's
  body. Write each commit as a focused, reviewable unit of work with a clear, imperative-mood
  summary line (and a short *why* body paragraph on non-trivial commits) — avoid noise like `wip` or
  `fix` that would leak into the squashed body. Leave auto-generated Dependabot commit messages as-is.

## Requirements for code changes

Only run tests, linters, and type checkers when they are **relevant to the files you actually
changed** — if a change only touches documentation (e.g. `.md` files), skip `pytest`, `ruff`, and
`mypy`. When you do change Python code, dependency manifests, or configuration, before considering
the change complete:
1. **Add or update unit tests** in `tests/test_utils.py` (API) or `LLSP-Worker/tests/` (worker) for
   any new or changed behavior.
2. **Add or update E2E coverage** in `tests/e2e/test_submission.py` when the change affects the
   submit/status flow or the Docker Compose wiring that suite exercises.
3. **Run the linter and type checker** (`ruff check .`, `ruff format .`,
   `mypy --strict LLSP-API LLSP-Worker --exclude LLSP-Worker/build`) and fix everything reported.
4. **Run the full unit and E2E suites.** Note this repo does **not** currently track coverage in CI
   (`.github/workflows/test.yml` runs plain `pytest` with no `--cov`/Codecov step), so there is no
   coverage percentage to compare against `main` — focus on confirming all tests still pass rather
   than a coverage delta.

## Pull request process

1. **Local validation** before opening a PR (when `.py` / `pyproject.toml` / container files are
   changed; skip for `.md`-only changes):
   ```shell
   conda run -n <env-name> pytest tests/test_utils.py
   conda run -n <env-name> pytest ./LLSP-Worker/tests
   conda run -n <env-name> ruff check .
   conda run -n <env-name> ruff format .
   conda run -n <env-name> mypy --strict LLSP-API LLSP-Worker --exclude LLSP-Worker/build
   ```
   Note: the CI workflow (`.github/workflows/lint.yml`) also runs `ruff format .`,
   `ruff check --fix`, and `mypy --strict LLSP-API LLSP-Worker --exclude LLSP-Worker/build` on every
   non-`main` push and auto-commits any fixes back to the branch as `"Formatting and linting commit"`.
2. **PR title**: a clear, concise description in normal grammar/sentence case (e.g. `Add api key
   auth`, `Include mantid in llsp worker`). Do not use `snake_case` for PR titles.
3. **PR description**: use the org-wide default template from `fiaisis/.github`
   (`.github/pull_request_template.md` — no local override in this repo), which is just
   `Closes # <Issue Number>` followed by a `## Description` section. Ask the user for the issue
   number if one isn't evident from the task, or confirm there is none to link.
4. **AI-assistance label**: attach a label to the PR indicating that it was made with the assistance
   of AI. Check existing labels first with `gh label list` (e.g. `AI` or `AI_code` in this org) and
   apply the matching label via `gh pr create --label <label>` or
   `gh pr edit <number> --add-label <label>`; if the repo does not have an AI label yet, create one
   first (`gh label create "AI" --description "Created with the assistance of AI"`).

## Handling Dependabot PRs

Dependabot creates weekly PRs grouped as `python-packages`, `action-packages`, and `docker` per
`.github/dependabot.yml`. When asked to handle these:

1. **List and identify**: `gh pr list` to find open Dependabot PRs.
2. **Review changes**: `gh pr diff <number>`, paying close attention to major version bumps in
   `LLSP-API/pyproject.toml`, `LLSP-Worker/pyproject.toml`, `LLSP-*/Dockerfile`, or
   `.github/workflows/`.
3. **Validate**:
   - Python/dependency changes: `gh pr checkout <number>`, install updated dependencies
     (`pip install "./LLSP-API[all]" "./LLSP-Worker[all]"`), and run unit tests, `ruff`, and
     `mypy --strict` as in the PR process above.
   - Docker/Action changes: verify CI checks pass with `gh pr checks <number>`.
4. **Approve and merge** once validation passes:
   ```shell
   gh pr review <number> --approve
   gh pr merge <number> --merge
   ```
   Use `--admin` if blocked by branch protection (`gh pr merge <number> --merge --admin`).
5. **Clean up**: close redundant/superseded PRs with `gh pr close <number> --delete-branch`.
6. **Final verification**: checkout `main`, pull latest changes, and re-run the unit test suites to
   confirm `main` is green.

## General working practices

- Prefer the `read` tool (with `offset`/`limit`) over `sed -n`, `cat`, or similar shell one-liners
  when inspecting file contents, and prefer the `write` and `edit` tools over `bash` (`cat <<EOF`,
  `sed -i`, `echo >`), Python one-liners, or other non-tool-based commands whenever creating or
  modifying files.
- Ask the user a clarifying question whenever a task is ambiguous (e.g. whether a change applies to
  `LLSP-API`, `LLSP-Worker`, or both, or whether an issue number exists to link in a PR) rather than
  guessing.
- Keep dependency versions pinned with `==` in both subproject `pyproject.toml` files consistent
  with the existing style.

## Keeping this document up to date

If a change you make would make any information in this `AGENTS.md` inaccurate or incomplete —
e.g. a new endpoint or environment variable, a changed Celery task/queue contract, a changed
directory layout, a new/renamed CI workflow, an updated Dependabot grouping, a new sibling-repo
contract, or a different testing/linting command — update the relevant section of this file as part
of the same change. Treat it the same way you would treat `README.md`: documentation that goes stale
is worse than no documentation, so don't leave it to a future agent or PR to notice the drift.
