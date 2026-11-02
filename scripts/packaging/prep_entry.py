"""Frozen entry point, including the application's existing subprocess workers."""
import multiprocessing
import runpy
import sys


WORKERS = {
    "caelab_prep.adapters.gmsh_worker",
    "caelab_prep.adapters.msh_worker",
    "caelab_prep.application.mesh_candidates",
    "caelab_prep.application.structured_mesh_worker",
}


if __name__ == "__main__":
    multiprocessing.freeze_support()
    if len(sys.argv) >= 3 and sys.argv[1] == "-m":
        module = sys.argv[2]
        if module not in WORKERS:
            raise SystemExit("Unsupported packaged worker")
        sys.argv = [module, *sys.argv[3:]]
        runpy.run_module(module, run_name="__main__")
    else:
        from caelab_prep.cli import main
        raise SystemExit(main())
