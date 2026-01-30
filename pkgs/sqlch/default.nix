{ lib, python3Packages }:
python3Packages.buildPythonApplication {
  pname = "sqlch";
  version = "0.1.0";
  src = ../../.;
  
  pyproject = true;
  
  nativeBuildInputs = [
    python3Packages.setuptools
    python3Packages.wheel
  ];
  
  propagatedBuildInputs = [
    python3Packages.requests
    python3Packages.textual
  ];
  
  pythonImportsCheck = [ "sqlch" ];
  doCheck = false;
  
  meta = with lib; {
    description = "Headless radio + TUI streaming controller";
    license = licenses.mit;
    platforms = platforms.linux;
  };
}
