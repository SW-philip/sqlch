{ lib
, python3Packages
, fetchFromGitHub
}:

python3Packages.buildPythonApplication {
  pname = "sqlch";
  version = "0.1.1";

  src = fetchFromGitHub {
    owner = "SW-philip";
    repo  = "sqlch";
    rev   = "af71af5";
    sha256 = "sha256-QNCllTQBafEPcODI7UWlos98iOzni8O7kvZ7tZ9RwOw=";
  };

  pyproject = true;

  # 🔧 THIS is what was missing
  nativeBuildInputs = [
    python3Packages.setuptools
    python3Packages.wheel
  ];

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

  meta = with lib; {
    description = "Headless radio + TUI streaming controller";
    license = licenses.mit;
    platforms = platforms.linux;
  };
}
