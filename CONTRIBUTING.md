# Contributing

Thanks for helping. Wrong numbers are the most important bugs here, so a report
with the inputs and your own arithmetic is very welcome.

## Setup

```bash
git clone https://github.com/gautamggg53/position-size-calc
cd position-size-calc
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest --cov
ruff check . && ruff format --check .
```

## Ground rules

- **Keep the library dependency-free.** PyYAML stays optional.
- **Every change to the maths needs a hand-worked test** in
  `tests/test_worked_examples.py`, with the arithmetic in a comment, and must
  keep the property tests in `tests/test_properties.py` passing. Do not derive
  expected values by running the code under test.
- **Safety first:** sizes are always rounded down and never exceed the risk or
  prop cap. A change that can round up will not be merged.
- **Presets are examples.** When adding or changing one, link a public
  contract-spec page (exchange or broker) in the PR, and keep the "example"
  wording in the file.
- Add a line under "Unreleased" in `CHANGELOG.md`.

## Releasing (maintainers)

1. Move "Unreleased" entries under a new version in `CHANGELOG.md` and bump
   `version` in `pyproject.toml` and `src/position_size_calc/__init__.py`.
2. `python -m build` and smoke-test the wheel in a fresh venv.
3. `git tag -a vX.Y.Z -m "vX.Y.Z"` and push the tag.
