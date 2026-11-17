"""run_j2.py <mask> <wmask> [more mybench args]: set env, run mybench j2_bg."""
import os
import sys

mask, wmask = sys.argv[1], sys.argv[2]
os.environ["J_MASK"] = mask
os.environ["J_WMASK"] = wmask
sys.argv = [sys.argv[0], "j2_bg", "--tag", f"_{mask}{wmask}", *sys.argv[3:]]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mybench  # noqa: E402

mybench.main()
