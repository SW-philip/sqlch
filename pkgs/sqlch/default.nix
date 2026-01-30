python3Packages.buildPythonApplication {
  pname = "sqlch";
  version = "0.1.1"; # ← bump this

  src = ../..;  # ← relative to pkgs/sqlch, this now points at ~/src/sqlch

  pyproject = true;

  propagatedBuildInputs = [
    python3Packages.requests
    python3Packages.textual
  ];

  pythonImportsCheck = [
    "sqlch"
    "sqlch.cli.main"
    "sqlch.tui.app"
  ];

  doCheck = false;
}
