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
    rev   = "840c9ff";
   sha256 = "sha256-9uZdlHjN4okjgvYgjfz8AzNdTjFP6Zi8j9px39o27WI=";
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
