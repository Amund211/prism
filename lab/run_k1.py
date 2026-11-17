"""run_k1.py <module> <bg|shadow> [mybench args]: shape matcher bench."""
import os
import sys

mod, mask = sys.argv[1], sys.argv[2]
os.environ["J_MASK"] = "shadow"
os.environ["J_WMASK"] = "0"
os.environ["J_FALLBACK"] = "1"
os.environ["K_MASK"] = mask
sys.argv = [sys.argv[0], mod, "--tag", f"_{mask}", *sys.argv[3:]]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mybench  # noqa: E402

mybench.main()
