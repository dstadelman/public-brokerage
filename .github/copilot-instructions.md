Activate the python venv before running any python commands:
`source .venv/Scripts/activate`

Run commands in the shell.py like this:
`source /C/MyProjects/public-brokerage/.venv/Scripts/activate && cd /c/MyProjects/public-brokerage && echo -e 'close_call_spread SPY --execute\ny\nexit' | python shell.py`

We only use the `unittest` framework for tests. DO NOT USE `pytest` or any other testing framework. Tests are right next to the code they test and called `*_test.py`.
