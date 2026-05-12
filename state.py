from enum import Enum, auto
from storage.session import load_session


class Mode(Enum):
    GLOBAL_FYP = auto()
    FOLLOWED_FYP = auto()
    CHAT = auto()
    ROOM = auto()
    PROFILE = auto()


class AppState:
    def __init__(self):
        self.mode = Mode.GLOBAL_FYP
        self.fyp_type = "global"
        self.current_chat = None
        self.current_room = None
        self.hold = False

        self.peers = []
        self.user = None
        self.pubkey = None
        self.apply_session(load_session())

    def apply_session(self, session):
        self.user = session["username"] if session else None
        self.pubkey = session["pubkey"] if session else None

    def refresh_session(self):
        session = load_session()

        if session:
            if (
                self.user != session["username"]
                or self.pubkey != session["pubkey"]
            ):
                self.apply_session(session)
                return "changed"
            return "same"

        if self.user or self.pubkey:
            self.apply_session(None)
            self.exit_chat()
            self.exit_room()
            self.exit_profile()
            return "cleared"

        return "none"

    def switch_fyp(self, fyp):
        if fyp not in ["global", "followed"]:
            raise ValueError("Invalid FYP type")
        self.fyp_type = fyp
        self.mode = Mode.GLOBAL_FYP if fyp == "global" else Mode.FOLLOWED_FYP

    def enter_chat(self, username):
        self.mode = Mode.CHAT
        self.current_chat = username

    def exit_chat(self):
        self.mode = Mode.GLOBAL_FYP
        self.current_chat = None

    def enter_room(self, room_name):
        self.mode = Mode.ROOM
        self.current_room = room_name

    def exit_room(self):
        self.mode = Mode.GLOBAL_FYP
        self.current_room = None

    def enter_profile(self):
        self.mode = Mode.PROFILE

    def exit_profile(self):
        self.mode = Mode.GLOBAL_FYP

    def toggle_hold(self):
        self.hold = not self.hold
        return self.hold
