Beep is a lightweight, anonymous social networking platform designed for terminal enthusiasts. Built for Python/Termux, it allows users (“Beepers”) to:
Create and share posts anonymously
Follow other users or browse the global feed
Comment, share, and quote posts
Chat privately or in rooms
Enjoy offline-friendly feeds using a hybrid local-first replication system
Posts are stored locally with optional replication for global and followed feeds, ensuring privacy, fast access, and offline availability.


python3 -m venv .venv
source .venv/bin/activate # for debian linux
venv\Scripts\activate.ps1 # for windows
pip install -r requirement.txt
python3 cli.py

