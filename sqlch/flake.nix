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
    packages.${system} = {
      sqlch = pkgs.callPackage ./pkgs/sqlch { };
      default = self.packages.${system}.sqlch;
    };

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
      ];
    };
  };
}
