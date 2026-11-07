"""Run the full pipeline. Any hard failure aborts before publish: the last
good committed JSON stays live on Pages."""
import subprocess, sys, pathlib

HERE = pathlib.Path(__file__).resolve().parent
STEPS = ["fetch_warn.py", "validate.py", "dedupe.py", "forecast.py",
         "fetch_bls.py", "fetch_fred.py", "fetch_gdelt.py", "build_json.py"]


def main():
    for step in STEPS:
        print(f"--- {step} ---", flush=True)
        r = subprocess.run([sys.executable, str(HERE / step)], cwd=HERE)
        if r.returncode != 0:
            print(f"PIPELINE FAILED at {step}", flush=True)
            return r.returncode
    print("pipeline ok", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
