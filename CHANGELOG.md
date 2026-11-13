# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- With `--target` and a commission, the output now also shows the R:R after
  commission (`reward / actual risk`), e.g. `R:R 2.00 (1.93 after commission)`,
  and JSON has `net_reward_to_risk`. The plain R:R is the price ratio, which
  overstates the trade's real payoff once round-turn commission is counted.

### Fixed

- Reject NaN and infinite inputs (balance, risk, prices, commission, rate, prop
  limits and instrument spec fields) with a clear error. Previously `inf` or
  `nan` crashed the CLI with a traceback, and a NaN daily-loss or drawdown
  limit was silently ignored, so the size was not capped by it.
- Preset files: numbers written as text are accepted, so a YAML value like
  `tick_size: 1e-5` (which PyYAML reads as a string) now works instead of
  failing with an unnamed "must be real number, not str" error. Booleans and
  other non-numbers in numeric fields are rejected with the field's name;
  previously `lot_step: true` was taken as 1 and later crashed with a traceback.
- `--open-risk` without `--daily-loss-left` or `--max-dd-left` is now an error.
  It was silently ignored, so the size did not account for the open risk.

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
