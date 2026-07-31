from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_windows_powershell_scripts_are_ascii_for_legacy_powershell():
    for name in ("setup.ps1", "run.ps1"):
        content = (PROJECT_ROOT / name).read_bytes()
        assert content.isascii(), f"{name} must remain ASCII for Windows PowerShell 5.1"
