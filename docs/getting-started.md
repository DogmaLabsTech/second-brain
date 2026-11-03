# Getting started: a checklist for a fresh computer

Follow it top to bottom. Each step says what you should see. An AI agent can follow it as written: run the command, compare the result, stop at the first step that does not match and report that step.

Tested here: Linux (Arch), with Python 3.14 and Node 26. Not yet tested: Ubuntu, macOS and WSL2. Part B is the path for a Windows PC with Ubuntu inside it (WSL2); run it there first and report any step that differs.

## Part A: any Linux or macOS

1. Python 3.12 or newer: python3 --version prints 3.12 or higher.
2. git: git --version prints a version.
3. Node 22.12 or newer: node --version prints v22.12 or higher.
4. The search tool: npm i -g @tobilu/qmd, then qmd --version prints a version.
5. Python packages: pip install pyyaml numpy (on a system where pip refuses, make a virtual environment first: python3 -m venv ~/.venvs/second-brain, then . ~/.venvs/second-brain/bin/activate).
6. Get the code: git clone https://github.com/DogmaLabsTech/second-brain.git and cd second-brain.
7. Check everything: ./install.sh prints "ok" for each needed tool and ends with "Ready." If it prints MISSING, fix that line and run it again.
8. Run the tests: bin/test. Every folder ends with "OK" (some tests are skipped; that is expected). The last lines are the Deck tests, also OK.
9. Look before you choose: bin/brain onboard --plan prints what it found and says "Nothing is ingested unless you choose it." Nothing is written.
10. Choose what goes in. Guided: bin/brain onboard. Without questions: bin/brain onboard --yes --notes ~/notes --sessions none (add --sessions claude to turn your Claude Code chats into notes). It ends with "qmd update ok".
11. Search: bin/brain search "a word from one of your notes" prints paths and snippets.
12. Optional, answers instead of snippets: install Ollama (ollama.com), run ollama pull qwen2.5:3b, then bin/brain ask "a question your notes can answer".
13. Optional, the map: see deck/README.md.

If you have no notes yet, make a small test folder: mkdir ~/try-notes and put one .md file in it, then use it in step 10.

## Part B: a Windows PC with Ubuntu inside (WSL2)

Run steps 1 to 5 inside the Ubuntu window, not in Windows.

1. In Windows PowerShell (as administrator): wsl --install -d Ubuntu, then restart if asked and open Ubuntu from the Start menu.
2. In Ubuntu: sudo apt update && sudo apt install -y python3 python3-venv python3-pip git curl
3. Node 22: install it with nvm (curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash, open a new terminal, then nvm install 22).
4. Python packages in a virtual environment (Ubuntu does not allow system-wide pip installs): python3 -m venv ~/.venvs/second-brain, then . ~/.venvs/second-brain/bin/activate, then pip install pyyaml numpy
5. The search tool: npm i -g @tobilu/qmd
6. Continue with Part A, step 6. Keep the virtual environment active in every new terminal (the . ~/.venvs/second-brain/bin/activate line).

Your Windows files are visible in Ubuntu under /mnt/c/Users/<you>/. Notes read faster from the Ubuntu home folder than from /mnt/c, so copy a test folder over for the first try.

## What to report back from a new machine

- The step number that first differed, and the exact text it printed.
- The output of ./install.sh --json.
- The last lines of bin/test (the "Ran N tests" and OK or FAILED lines for each folder).
- Whether step 11 found a note you know is there.
