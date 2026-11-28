{
  description = "SQLCH – streaming radio toolkit";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";
  };

  outputs = { self, nixpkgs }:
  let
    system = "x86_64-linux";
    pkgs = import nixpkgs { inherit system; };
  in
  {
    overlays.default = final: _prev: {
      sqlch = final.callPackage ./pkgs/sqlch { };
    };

    packages.${system} = {
      sqlch = pkgs.callPackage ./pkgs/sqlch { };
      default = self.packages.${system}.sqlch;
    };

    homeManagerModules.default = import ./nix/home.nix;

    apps.${system}.default = {
      type = "app";
      program = "${self.packages.${system}.sqlch}/bin/sqlch";
    };

    devShells.${system}.default = pkgs.mkShell {
      inputsFrom = [ self.packages.${system}.sqlch ];
      packages = with pkgs; [
        python3
        python3Packages.pip
        python3Packages.virtualenv
        python3Packages.pydbus
        python3Packages.pygobject3
        python3Packages.pytest
        glib
        gobject-introspection
        gtk4
        gtk4-layer-shell
        librsvg
      ];
      # must load before libwayland-client, which `import gi` pulls in
      GTK4_LAYER_SHELL = "${pkgs.gtk4-layer-shell}/lib/libgtk4-layer-shell.so";
    };
  };
}
