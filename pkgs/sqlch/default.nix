{ lib, pkgs, python3Packages, fetchFromGitHub }:

python3Packages.buildPythonApplication {
  pname = "sqlch";
  version = "0.1.1";

  src = fetchFromGitHub {
    owner = "SW-philip";
    repo  = "sqlch";
    rev   = "840c9ff";  # pinned commit
    sha256 = lib.fakeSha256;
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

  # Runtime tools sqlch shells out to
  buildInputs = [
    pkgs.mpv
    pkgs.socat
    pkgs.procps
    pkgs.mpvScripts.mpris
  ];

  # Inject runtime paths cleanly (no hardcoded /nix/store in Python)
  postFixup = ''
    wrapProgram $out/bin/sqlch \
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
