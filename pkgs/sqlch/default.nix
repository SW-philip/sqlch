{ lib, python3Packages, fetchFromGitHub }:

python3Packages.buildPythonApplication {
  pname = "sqlch";
  version = "0.1.0";

  src = fetchFromGitHub {
    owner = "SW-philip";
    repo = "sqlch";
    rev = "main";
    sha256 = "sha256-REPLACE_ME";
  };

  pyproject = true;

  nativeBuildInputs = [
    python3Packages.setuptools
    python3Packages.wheel
  ];

  propagatedBuildInputs = [
    python3Packages.requests
    python3Packages.textual
  ];

  # sanity check: fails early if imports are broken
  pythonImportsCheck = [ "sqlch" ];

  doCheck = false;

  meta = with lib; {
    description = "Headless radio + TUI streaming controller";
    license = licenses.mit;
    platforms = platforms.linux;
  };
}
