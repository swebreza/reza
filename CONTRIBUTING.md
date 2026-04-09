# Contributing to reza

Thank you for your interest in contributing to reza.

## Development Setup

```bash
git clone https://github.com/suwebreza/reza
cd reza
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest
pytest --cov=reza --cov-report=term-missing
```

## Project Structure

```
reza/
├── reza/
│   ├── cli.py          # Click CLI — all user-facing commands
│   ├── schema.py       # DB schema + connection utilities
│   ├── init_db.py      # Project scanning and initialization
│   ├── watcher.py      # Real-time file watcher (watchdog)
│   ├── session.py      # Session CRUD
│   ├── query.py        # Query functions
│   ├── update.py       # File update for git hooks
│   └── export.py       # Export to markdown / JSON
├── integrations/       # Tool-specific integration guides
├── tests/              # pytest test suite
├── pyproject.toml
└── README.md
```

## Adding a Tool Integration

1. Create `integrations/TOOLNAME/README.md`
2. Cover at minimum:
   - Setup steps
   - How to inject context into the tool
   - Cross-LLM handoff workflow (`reza session` commands)
   - Any tool-specific config files
3. Add the tool to the table in `integrations/README.md`
4. Add the tool to the main `README.md` integrations table

## Adding Purpose Extraction for a Language

In `reza/init_db.py`, the `extract_purpose()` function uses regex patterns.
To add a new language:

1. Add the file extension to `TEXT_EXTENSIONS`
2. Add a pattern to `extract_purpose()` for that extension
3. Add a test case in `tests/test_init.py`

## Pull Request Guidelines

- Keep PRs focused — one feature or fix per PR
- Add tests for new functionality
- Run `pytest` before submitting
- Run `black reza/ tests/` and `ruff check reza/ tests/` for formatting

## Reporting Bugs

Open an issue at https://github.com/suwebreza/reza/issues with:
- Python version
- OS
- `reza --version` output
- Steps to reproduce
- Expected vs actual behavior
