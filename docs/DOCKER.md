## Current merged validation

See [RELEASE_VERIFICATION.md](RELEASE_VERIFICATION.md) for the October 29 local Linux ARM64 build, test and persistence results. Historical statements below about Docker being unavailable describe the earlier workstation check. The merged candidate has now been built locally.

# Browser extension packaging handoff

Base Docker work is Xiaolong's commit `d2c110f` on `xiaolong/docker`.
Yong's integration preserves that packaging and adds browser CSS/config, a
`SILVERFILE_DATA_DIR=/app/state` dashboard root (so uploads are a real writable
subdirectory of the named volume), and feature-branch CI. CLI database symlinks
still point at the same volume. Upload paths remain inside the validated root;
no upload symlink exception was added. Do not put keys in image/build arguments.

The upstream Linux validation below applies to Xiaolong's original snapshot.
The browser-extended runtime at commit `6fe6c58` subsequently passed the complete
Linux GitHub Actions build, dependency check, offline tests and dashboard health:
[Docker CI run 40782142415](https://github.com/DhruvRawat418/Assignment7_taxsystem/actions/runs/40782142415).
This macOS workstation has no local Docker engine. The team should rebuild after
any later runtime merge and still perform both live-key demos before release.
Use `dhruv/submission-integration` when cloning the browser extension. After starting,
click **New case**; the old CLI creation instructions below are optional.

# Run SilverFile with Docker

Run commands from the repository root on the `dhruv/submission-integration` branch. Install Docker Desktop (macOS/Windows) or Docker Engine with the Compose plugin (Linux). In GitHub Codespaces, use the terminal in this repository. Check that `docker info` and `docker compose version` succeed.

For a fresh checkout:

```sh
git clone --branch dhruv/submission-integration https://github.com/DhruvRawat418/Assignment7_taxsystem.git
cd Assignment7_taxsystem
```

The image contains Python 3.12, the integrated agents, local OCR, the MCP calculation server, PDF template, and Streamlit dashboard. The MCP server runs as a child process inside the same container. No separate MCP service is needed.

## Build and run without an API key

```sh
docker compose build
docker compose run --rm --no-deps app python -m pip check
docker compose run --rm --no-deps app python -m pytest tests -q
docker compose up -d
docker compose ps
```

The dashboard is at http://localhost:8501. In Codespaces, open port 8501 from the Ports panel and keep its visibility Private. The dashboard has no staff login and is intended for local, single-operator use.

An empty dashboard is expected until a saved interview has been handed off. Build, tests, the dashboard, and the default rule-based intake work without an OpenAI key. Tests use fake provider responses where required; passing them does not verify the live OpenAI reviewer.

## Run the interview in the same environment

```sh
docker compose run --rm --no-deps app python -m demo.run_intake
```

Use the synthetic answers and `demo/w2_clean.jpg` from [README_TEAM.md](../README_TEAM.md). Paths refer to files inside the image. Use synthetic data only. The image already contains the team's fixtures; host Downloads/Desktop files are not mounted.

## Enable the live reviewer when ready

The current reviewer requires an authorized OpenAI key with available credits and model access. Use your own project key. Follow step 4 of [README_TEAM.md](../README_TEAM.md) to set `OPENAI_API_KEY` securely in the terminal; do not paste the key into chat or a command argument.

Compose passes the terminal variable to containers at runtime. The key is not needed during the build and is not included in the image. This Compose file also supports Docker Compose's normal `.env` interpolation, but an env file must remain local and uncommitted. Never bake credentials into a Dockerfile.

After setting the key, recreate the dashboard so it receives the updated environment:

```sh
docker compose up -d --force-recreate
docker compose run --rm --no-deps app python -m demo.run_intake --handoff team-clean-001
```

The model remains `gpt-4.1-mini`; an optional `SILVERFILE_REVIEW_MODEL` environment variable changes it. Review, correction, and PDF download behavior are the same as [README_TEAM.md](../README_TEAM.md). With no working key, the live review cannot finish and a case must remain blocked; Docker does not bypass that check.

## Keep interviews and workflow state

The dashboard and every `docker compose run` command share the `case_data` volume. It stores both `intake_sessions.db` and `workflow_sessions.db`, including SQLite journal files. Restarting, recreating, or rebuilding the containers preserves this volume.

```sh
docker compose down
docker compose up -d
```

Use the same checkout/project name to reopen the same volume. Do not add `--volumes` or `-v` to `down` when you want to preserve saved cases. This setup starts with its own empty volume; it does not import existing host databases. Stop other writers before making a SQLite backup.

## Logs, updates, and alternate ports

```sh
docker compose logs --tail=100 app
docker compose up -d --build
```

If port 8501 is occupied, set `SILVERFILE_PORT=8502` in your terminal and run `docker compose up -d`; then open http://localhost:8502. The host binding stays on `127.0.0.1`.

`requirements-docker.txt` locks the full integrated dependency set for Python 3.12 on Linux. It is separate from the older extraction-only `requirements-lock.txt`. After changing the team's requirements, regenerate this lock in Linux, rebuild, and rerun the full tests. Rebuild the Docker branch after integrating later teammate changes.

## Validation

Validated on October 28, 2026 in a Linux amd64 Codespace:

- Image build and `pip check` passed. The image runs as the non-root `silverfile` user.
- All 274 tests and 21 subtests passed with container networking disabled, including real OCR and MCP subprocess tests. Pytest reported one harmless cache-directory permission warning because application source is owned by root.
- The dashboard health check passed before and after container recreation.
- A real rule-based interview, W-2 extraction, computation, and deterministic audit completed. With no API key, the live reviewer correctly left the case `blocked` with `provider_failed` owned by `adversarial`.
- After force-killing and recreating the test container, saved interview and computation hashes were identical. Both databases passed SQLite integrity checks, and committed transactions held only in WAL files were recovered from the volume.

`.github/workflows/docker.yml` automates image build, dependency checks, the full offline suite, and dashboard health on GitHub. The persistence check above was also run separately against an isolated synthetic test volume.

An API key is deliberately absent from the offline checks. Live provider availability and a successful paid review still need the key owner's separate verification. Docker Desktop on macOS/Windows and ARM64 have not been validated by these Linux amd64 checks.
