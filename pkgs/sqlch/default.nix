{ lib
, python3Packages
, mpv
}:

python3Packages.buildPythonApplication {
  pname = "sqlch";
  version = "0.1.0";

  src = lib.cleanSource ../..;

  pyproject = true;

  nativeBuildInputs = with python3Packages; [
    setuptools
    wheel
  ];

  propagatedBuildInputs =
    (with python3Packages; [
      requests
      rich
    ]) ++ [
      mpv
    ];

  pythonImportsCheck = [ "sqlch" ];

  meta = with lib; {
    description = "Streaming radio toolkit";
    license = licenses.mit;
    platforms = platforms.linux;
    mainProgram = "sqlch";
  };
}
