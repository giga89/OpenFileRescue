# Contributing to OpenFileRescue

Thank you for your interest in contributing to **OpenFileRescue**! We welcome contributions from developers, forensic enthusiasts, and users worldwide.

---

## 🧭 How to Contribute

### 1. Reporting Bugs
- Please check existing issues before opening a new one.
- Provide clear reproduction steps, storage device details (capacity, filesystem), OS version, and any error traces.
- Use our [Bug Report Template](.github/ISSUE_TEMPLATE/bug_report.yml).

### 2. Suggesting Features & File Parsers
- We love new file format parsers! If you'd like to add support for a new format (e.g. specialized camera RAWs, audio containers, archives):
  1. Check `openfilerescue/core/parsers/base.py` for the `BaseParser` interface.
  2. Implement `match(header_sample)` for fast signature filtering.
  3. Implement `parse(reader, offset)` to safely calculate exact byte boundaries and extract metadata.
  4. Add automated unit tests in `tests/`.

### 3. Development Setup
```bash
# Clone repository
git clone https://github.com/giga89/OpenFileRescue.git
cd OpenFileRescue

# Run automated unit tests
python3 -m unittest discover -s tests -v

# Run the CLI demo
python3 run.py --demo
```

### 4. Code Standards & Guidelines
- **Zero Mandatory External Dependencies**: The core carving engine must run on standard Python 3 without requiring third-party compiled packages (libraries like Pillow are optional enhancements).
- **Clean-Room Verification**: Do NOT copy code from proprietary or copyleft (GPL) tools. All format decoders must be written from scratch based on publicly documented RFCs and ISO standards.
- **Hardware Safety**: Any code interacting with physical media MUST enforce strict read-only access (`O_RDONLY`).

---

## Pull Request Process
1. Fork the repository and create your branch from `main`.
2. Ensure all tests pass (`python -m unittest discover -s tests -v`).
3. Submit your PR with a clear summary of changes and benefits.
