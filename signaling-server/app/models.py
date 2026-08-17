from typing import Literal, Union

from pydantic import BaseModel


class CreateSessionMessage(BaseModel):
    type: Literal["create-session"] = "create-session"


class SessionCreatedMessage(BaseModel):
    type: Literal["session-created"] = "session-created"
    session_id: str


class JoinSessionMessage(BaseModel):
    type: Literal["join-session"] = "join-session"
    session_id: str


class PeerJoinedMessage(BaseModel):
    type: Literal["peer-joined"] = "peer-joined"


class SdpMessage(BaseModel):
    type: Literal["offer", "answer"]
    sdp: str


class IceCandidateMessage(BaseModel):
    type: Literal["ice-candidate"] = "ice-candidate"
    candidate: str
    sdp_mid: str | None = None
    sdp_mline_index: int | None = None


class SessionExpiredMessage(BaseModel):
    type: Literal["session-expired"] = "session-expired"
    reason: str


class PeerDisconnectedMessage(BaseModel):
    type: Literal["peer-disconnected"] = "peer-disconnected"


InboundMessage = Union[CreateSessionMessage, JoinSessionMessage, SdpMessage, IceCandidateMessage]

OutboundMessage = Union[
    SessionCreatedMessage,
    PeerJoinedMessage,
    SdpMessage,
    IceCandidateMessage,
    SessionExpiredMessage,
    PeerDisconnectedMessage,
]

_INBOUND_MODELS: dict[str, type[BaseModel]] = {
    "create-session": CreateSessionMessage,
    "join-session": JoinSessionMessage,
    "offer": SdpMessage,
    "answer": SdpMessage,
    "ice-candidate": IceCandidateMessage,
}


def parse_inbound_message(raw: dict) -> InboundMessage:
    model = _INBOUND_MODELS.get(raw.get("type"))
    if model is None:
        raise ValueError(f"Unknown message type: {raw.get('type')!r}")
    return model.model_validate(raw)
