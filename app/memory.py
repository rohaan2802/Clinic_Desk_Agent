"""Message storage only. Students must use these messages in their model prompt."""
from collections import OrderedDict
from langchain_core.messages import HumanMessage, AIMessage
class Memory:
    def __init__(self):
        self.sessions = OrderedDict()
    def get(self, session):
        return list(self.sessions.get(session, []))
    def add(self, session, user, assistant):
        messages = self.get(session) + [HumanMessage(content=user), AIMessage(content=assistant)]
        # Six recent turns; also enforce a character ceiling (not a token counter).
        while len(messages) > 12 or sum(len(str(m.content)) for m in messages) > 24000:
            messages = messages[2:]
        self.sessions[session] = messages
        self.sessions.move_to_end(session)
        while len(self.sessions) > 100:
            self.sessions.popitem(last=False)
    def clear(self, session):
        self.sessions.pop(session, None)
