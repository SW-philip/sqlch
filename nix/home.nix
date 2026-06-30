{ config, lib, pkgs, ... }:
let
  cfg = config.sqlch.gui;

  sqlchGuiPython = pkgs.python3.withPackages (ps: with ps; [ pygobject3 ]);

  launcher = pkgs.writeShellScriptBin "sqlch-gui" ''
    export GI_TYPELIB_PATH="${pkgs.gtk4-layer-shell}/lib/girepository-1.0:${pkgs.gtk4}/lib/girepository-1.0:${pkgs.gdk-pixbuf}/lib/girepository-1.0:${pkgs.pango}/lib/girepository-1.0:${pkgs.graphene}/lib/girepository-1.0:${pkgs.harfbuzz}/lib/girepository-1.0:$GI_TYPELIB_PATH"
    export LD_LIBRARY_PATH="${pkgs.gtk4-layer-shell}/lib:${pkgs.graphene}/lib:$LD_LIBRARY_PATH"
    export SQLCH_GUI_PALETTE="${cfg.palettePath}"
    export PYTHONPATH="${../.}:$PYTHONPATH"
    exec ${sqlchGuiPython}/bin/python3 -m sqlch_gui "$@"
  '';

  toggle = pkgs.writeShellScriptBin "sqlch-gui-toggle" ''
    PIDFILE="''${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/sqlch/gui.pid"

    if [ -f "$PIDFILE" ]; then
        pid=$(cat "$PIDFILE")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid"
            rm -f "$PIDFILE"
            exit 0
        fi
        rm -f "$PIDFILE"
    fi

    mkdir -p "''${PIDFILE%/*}"
    sqlch-gui &
    echo "$!" > "$PIDFILE"
  '';
in {
  options.sqlch.gui = {
    enable = lib.mkEnableOption "sqlch-gui GTK4 radio frontend";
    palettePath = lib.mkOption {
      type    = lib.types.str;
      default = "${config.home.homeDirectory}/.config/waybar/palette.sh";
      description = "Path to palette.sh for theming.";
    };
  };

  config = lib.mkIf cfg.enable {
    home.packages = [ launcher toggle ];
  };
}
