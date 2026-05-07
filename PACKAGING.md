# Packaging qwen_cov_agent

The packaged executable must include `auto_func_cov.py` as a bundled data file.
The agent can still generate and apply LLM code patches after packaging because
all patch files are written under the target project `sim` directory, not beside
the executable.

## PyInstaller example

```bash
pyinstaller --onefile qwen_cov_agent.py --add-data "auto_func_cov.py:."
```

On Windows use `;` instead of `:` in `--add-data`:

```powershell
pyinstaller --onefile qwen_cov_agent.py --add-data "auto_func_cov.py;."
```

## Runtime behavior

- Mapping reports are written to the target project:
  - `logs/case_code_map.json`
  - `logs/case_code_map.md`
- LLM patches are written to:
  - `logs/llm_code_patch.diff`
- Patches are checked so every touched path stays under the active project root.
- Interactive mode asks before applying an LLM patch.
- Non-interactive mode writes the patch but does not apply it unless
  `--apply-llm-patch` is passed.
- When packaged, the executable invokes the bundled `auto_func_cov.py` through
  its internal `--run-auto-func-cov` entrypoint.
