# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Reproducible Docker Compose deployment with a non-root, read-only runtime.
- Python linting, formatting, type checking, coverage, and multi-version CI.
- Strict frontend compiler options and runtime validation for untrusted browser state.
- Open-source contribution, conduct, security, issue, and pull-request guidance.

### Changed

- Split backend configuration, domain models, API models, and WebSocket management into focused modules.
- Split frontend catalog data and client services from UI rendering.
- Added precise HTTP error statuses and baseline browser security headers.

### Removed

- The platform-specific virtual environment formerly committed to version control.
