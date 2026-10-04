"""Message storage only. Students must use these messages in their model prompt."""
from collections import OrderedDict
from langchain_core.messages import HumanMessage, AIMessage

MAX_TURNS = 100
MAX_MESSAGES = MAX_TURNS * 2  # 100 user + 100 agent
MAX_CHARS = 200000
MAX_SESSIONS = 100


class Memory:
    def __init__(self):
        self.sessions = OrderedDict()

    def get(self, session):
        return list(self.sessions.get(session, []))

    def add(self, session, user, assistant):
        messages = self.get(session) + [HumanMessage(content=user), AIMessage(content=assistant)]
        # Sliding window: drop the oldest turn. Chat is not reset or deleted.
        while len(messages) > MAX_MESSAGES or sum(len(str(m.content)) for m in messages) > MAX_CHARS:
            messages = messages[2:]
        self.sessions[session] = messages
        self.sessions.move_to_end(session)
        while len(self.sessions) > MAX_SESSIONS:
            self.sessions.popitem(last=False)

    def clear(self, session):
        self.sessions.pop(session, None)
