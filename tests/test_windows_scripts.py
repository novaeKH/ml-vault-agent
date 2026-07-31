from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_windows_powershell_scripts_are_ascii_for_legacy_powershell():
    for name in ("setup.ps1", "run.ps1"):
        content = (PROJECT_ROOT / name).read_bytes()
        assert content.isascii(), f"{name} must remain ASCII for Windows PowerShell 5.1"


def test_setup_suppresses_expected_native_probe_failures():
    content = (PROJECT_ROOT / "setup.ps1").read_text(encoding="ascii")

    assert "function Test-NativeCommand" in content
    assert '$ErrorActionPreference = "SilentlyContinue"' in content
    assert "Test-NativeCommand -Command $command -Arguments $probeArguments" in content
    assert 'Test-NativeCommand -Command "ollama"' in content
