# Contributing to pipecat-floe

Thanks for your interest in contributing to Floe's Pipecat services (`FloeLLMService`, `FloeTTSService`, `FloeSTTService`).

## Getting Started

```bash
git clone https://github.com/Floe-Labs/pipecat-floe.git
cd pipecat-floe
pip install -e ".[dev]"
```

## Development

```bash
ruff check src/            # Lint
ruff format src/           # Format
python -c "import pipecat_floe"   # Import smoke test
python -m build            # Verify the package builds
```

To run the example bot, see [`examples/README.md`](examples/README.md).

## Pull Requests

1. Fork the repo and create your branch from `main`
2. Keep changes focused; match the existing style
3. Ensure `ruff check src/` passes and the package imports cleanly
4. Write a clear PR description explaining the change

## Code Style

- Python 3.10+
- Type hints on all public functions
- Full docstrings on public classes and methods
- Follow existing patterns in `src/pipecat_floe/`

## Reporting Bugs

Open a GitHub issue with:
- Steps to reproduce
- Expected vs actual behavior
- `pipecat-ai` version, Python version, and OS

## Security Issues

See [SECURITY.md](SECURITY.md) — do **not** open a public issue for security vulnerabilities.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
