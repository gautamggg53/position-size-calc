# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-03

### Added

- `psize` CLI and `position_size_calc` library, no runtime dependencies.
- Sizing for forex (pip value including JPY pairs, cross-currency conversion
  with a user-supplied rate, exact conversion for base-currency accounts), CFDs,
  indices and metals (contract size, tick size/value), futures (tick value),
  and stocks/crypto (units).
- Stop as a price or a distance in pips, points or ticks; risk as % or a fixed
  amount; optional round-turn commission counted as risk.
- Size rounded down to the lot step, with min/max lot handling; actual risk
  after rounding; reward and R:R to an optional target.
- Prop mode: cap size by remaining daily-loss and max-drawdown room (minus open
  risk) and report which limit binds.
- Example instrument presets (JSON; YAML supported with PyYAML), clearly
  labelled as examples to check against broker contract specs.
- Hand-worked example tests and hypothesis property tests.
