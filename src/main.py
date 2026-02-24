import multiprocessing as mp

from whisperdictation.app import main

if __name__ == "__main__":
    mp.freeze_support()
    main()
