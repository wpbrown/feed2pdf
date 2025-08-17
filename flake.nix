{
  description = "feed2pdf dev env and app";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.05";
  };

  outputs =
    { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
      python = pkgs.python313;
      pythonEnv = python.withPackages (
        ps: with ps; [
          click
          sh
          yaspin
        ]
      );

      runtimePackages = with pkgs; [
        pythonEnv
        img2pdf
        usbutils
        imagemagick
        pdfarranger
        sane-frontends
      ];

      runScript = pkgs.writeShellApplication {
        name = "feed2pdf";
        runtimeInputs = runtimePackages;
        text = ''
          exec python ${./main.py} "$@"
        '';
      };
    in
    {
      devShells.${system}.default = pkgs.mkShell {
        packages = runtimePackages;
      };

      packages.${system}.default = runScript;
      apps.${system}.default = {
        type = "app";
        program = "${runScript}/bin/feed2pdf";
      };

      formatter.${system} = pkgs.nixfmt;
    };
}
