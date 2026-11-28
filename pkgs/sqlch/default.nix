{ lib
, python3Packages
, gobject-introspection
, mpv
, mpvScripts
, procps
, ffmpeg
, playerctl
, yt-dlp
}:

python3Packages.buildPythonApplication {
  pname = "sqlch";
  version = "0.2.0";

  src = lib.fileset.toSource {
    root = ../..;
    fileset = lib.fileset.unions [ ../../pyproject.toml ../../sqlch ];
  };

  pyproject = true;

  build-system = [ python3Packages.setuptools ];
  nativeBuildInputs = [ gobject-introspection ];

  dependencies = with python3Packages; [
    requests
    textual
    pygobject3
    pydbus
  ];

  # The code calls pkill, ffmpeg/ffprobe, playerctl and yt-dlp by name.
  # SQLCH_YTDLP / SQLCH_PLAYERCTL still override the last two.
  makeWrapperArgs = [
    "--prefix" "PATH" ":" (lib.makeBinPath [ procps ffmpeg playerctl yt-dlp ])
    "--set" "MPV_BIN" "${mpv}/bin/mpv"
    "--set" "SQLCH_MPRIS_PLUGIN" "${mpvScripts.mpris}/share/mpv/scripts/mpris.so"
  ];

  pythonImportsCheck = [ "sqlch" "sqlch.cli.main" "sqlch.tui.app" ];

  doCheck = false;

  meta = {
    description = "Headless radio + TUI streaming controller";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
    mainProgram = "sqlch";
  };
}
