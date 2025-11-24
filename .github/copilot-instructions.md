Activate the python venv before running any python commands:
`source .venv/Scripts/activate`

Run commands in the shell.py like this:
`source /C/MyProjects/public-brokerage/.venv/Scripts/activate && cd /c/MyProjects/public-brokerage && echo -e 'close_call_spread SPY --execute\ny\nexit' | python shell.py`

We only use the `unittest` framework for tests. DO NOT USE `pytest` or any other testing framework. Tests are right next to the code they test and called `*_test.py`.

DO NOT TRY TO PIPE OUTPUT of `shell.py` - there are emojis that screw up piping. You can pipe to `shell.py` ok.

THIS WILL NOT WORK

`cd /c/MyProjects/public-brokerage && source .venv/Scripts/activate && printf 'close_position NOK 2025-11-21 7 C 1\nn\nexit\n' | python shell.py 2>&1 | tail -60`

THERE IS `| tail -60` AT THE END
