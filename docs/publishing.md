# Publishing Beep To PyPI

Beep publishes to PyPI through GitHub Actions and PyPI Trusted Publishing.

## Package Metadata

The package name is:

```text
beep-cli
```

The console command is:

```text
beep
```

The first public release should use:

```text
0.1.0
```

PyPI versions are immutable. Once `0.1.0` is uploaded, any fix must use a new
version such as `0.1.1`.

## PyPI Trusted Publisher

Create or reserve the project on PyPI, then add a trusted publisher with:

```text
Owner: aadaam17
Repository name: beep
Workflow name: publish-pypi.yml
Environment name: pypi
```

The workflow uses GitHub OIDC, so no PyPI API token is stored in GitHub secrets.

## Release Flow

1. Make sure `pyproject.toml` has the intended version.
2. Push the release commit to GitHub.
3. Create and push a matching tag:

   ```text
   git tag v0.1.0
   git push origin v0.1.0
   ```

4. Create a GitHub release for `v0.1.0`.
5. Publishing starts when the GitHub release is published.
6. Confirm the package at:

   ```text
   https://pypi.org/project/beep-cli/
   ```

## Local Checks

Before tagging, run:

```text
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
```

Then install from the built wheel in a fresh environment or with pipx:

```text
pipx install dist/*.whl
beep
```
