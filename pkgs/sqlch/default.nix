{ lib, pkgs, python3Packages, fetchFromGitHub }:

python3Packages.buildPythonApplication {
  pname = "sqlch";
  version = "0.1.1";

  src = fetchFromGitHub {
    owner = "SW-philip";
    repo  = "sqlch";
<<<<<<< HEAD
    rev   = "840c9ff";
    sha256 = lib.fakeSha256;
=======
    rev   = "main";
   sha256 = "lib.fakeSha256;"
>>>>>>> 5d8091c (change sqlch/defualt.nix)
  };

  pyproject = true;

  nativeBuildInputs = with python3Packages; [
    setuptools
    wheel
  ];

  propagatedBuildInputs = with python3Packages; [
    requests
    textual
  ];

  # Tools sqlch uses at runtime
  runtimeDeps = [
    pkgs.mpv
    pkgs.socat
    pkgs.procps
    pkgs.mpvScripts.mpris
  ];

  buildInputs = runtimeDeps;

  postFixup = ''
    wrapProgram $out/bin/sqlch \
      --prefix PATH : ${lib.makeBinPath runtimeDeps} \
      --set MPV_BIN ${pkgs.mpv}/bin/mpv \
      --set SQLCH_MPRIS_PLUGIN ${pkgs.mpvScripts.mpris}/share/mpv/scripts/mpris.so
  '';

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
