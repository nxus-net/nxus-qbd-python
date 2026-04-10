## Release PR Checklist

### Summary
- [ ] This PR is intended for a Python SDK release or public-repo readiness pass
- [ ] The version in `pyproject.toml` is intentionally set for this release
- [ ] `CHANGELOG.md` has been updated, or the team has explicitly decided to skip it for this release

### Public Repo Hygiene
- [ ] No secrets, `.env` contents, real API keys, or real connection IDs are included
- [ ] No private monorepo-only validation assets are included from `private-validation/`
- [ ] No backup files or editor debris are included
- [ ] Internal-only docs/files have been excluded from the public repo as needed

### Packaging
- [ ] Clean install works in a fresh environment

```powershell
uv pip install -e .
python -c "import nxus_qbd; import nxus_qbd.models; print('ok')"
```

- [ ] Runtime dependencies in `pyproject.toml` are correct
- [ ] License and package metadata are correct

### Codegen / Models
- [ ] `spec/openapi.json` is current
- [ ] Models were regenerated successfully

```powershell
uv run --extra codegen python scripts/generate.py --url https://localhost:7242/openapi/v1.json
```

- [ ] Generated models import cleanly
- [ ] Enum/discriminator generation looks correct
- [ ] Datetime parsing behavior has been validated against the current API output

### Unit / Public-Safe Tests
- [ ] Unit and public-safe tests pass

```powershell
uv run --extra dev python -m pytest -q
```

- [ ] Examples and package compile cleanly

```powershell
uv run --extra dev python -m compileall nxus_qbd examples
```

### Docs / Examples
- [ ] `README.md` matches the current SDK behavior
- [ ] Default production URL is `https://api.nx-us.net/`
- [ ] Development environment handling is documented
- [ ] Examples use the current Pythonic API surface
- [ ] `auth_setup.py` is present and documented
- [ ] Regeneration instructions are accurate and do not reference removed tooling

### Private Release Validation
- [ ] Private validation has been run from the monorepo-only harness

```powershell
uv run --extra dev python -m pytest ..\private-validation\nxus-qbd-python -q
```

- [ ] At least one real mutation flow has been validated against a real company file
- [ ] Vendor CRUD has been validated
- [ ] One transaction flow has been validated
- [ ] One or more reports have been validated
- [ ] Auth/connection flow has been validated if platform changes are included

### Final Release Gate
- [ ] The branch is ready to merge
- [ ] The pushed remote state matches the local validated state
- [ ] The repo is safe to make public after merge/push

### Notes
Add any release-specific risks, skipped validations, or follow-up items here.
