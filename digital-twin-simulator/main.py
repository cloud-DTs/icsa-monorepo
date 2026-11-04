import os
from dotenv import load_dotenv
load_dotenv()

from simulator.simulator import main

if __name__ in {"__main__", "__mp_main__"}:
    main()