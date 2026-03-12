import sys
from pathlib import Path
from spec2rtl.pipeline import Spec2RTLPipeline

def run_test():
    with open("Prob002_alu_prompt.txt", "r") as f:
        spec_text = f.read()

    pipeline = Spec2RTLPipeline()
    for run_id in range(1, 4):
        print(f"\n\n================ RUN {run_id} ================\n\n")
        try:
            pipeline.run_from_text(spec_text)
            print(f"RUN {run_id} SUCCESS")
        except Exception as e:
            print(f"RUN {run_id} FAILED: {e}")
            sys.exit(1)

if __name__ == "__main__":
    run_test()
