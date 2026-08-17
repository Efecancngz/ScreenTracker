from typing import Any, Literal, Union

from pydantic import BaseModel


class CreateSessionMessage(BaseModel):
    type: Literal["create-session"] = "create-session"


class SessionCreatedMessage(BaseModel):
    type: Literal["session-created"] = "session-created"
    session_id: str


class JoinSessionMessage(BaseModel):
    type: Literal["join-session"] = "join-session"
    session_id: str
    device_id: str | None = None


class PeerJoinedMessage(BaseModel):
    type: Literal["peer-joined"] = "peer-joined"


class SdpMessage(BaseModel):
    type: Literal["offer", "answer"]
    sdp: str


class IceCandidateMessage(BaseModel):
    type: Literal["ice-candidate"] = "ice-candidate"
    # The browser sends RTCIceCandidate.toJSON() verbatim, i.e. an
    # RTCIceCandidateInit object: {candidate, sdpMid, sdpMLineIndex,
    # usernameFragment}. The server never inspects it — it only relays the raw
    # message to the peer — so an untyped mapping keeps the contract honest
    # without duplicating the browser's schema here.
    candidate: dict[str, Any]


class SessionExpiredMessage(BaseModel):
    type: Literal["session-expired"] = "session-expired"
    reason: str


class PeerDisconnectedMessage(BaseModel):
    type: Literal["peer-disconnected"] = "peer-disconnected"


class RegisterHostMessage(BaseModel):
    type: Literal["register-host"] = "register-host"
    host_id: str


class AuthenticateMessage(BaseModel):
    type: Literal["authenticate"] = "authenticate"
    host_id: str
    device_id: str
    token: str


class PairApprovedMessage(BaseModel):
    type: Literal["pair-approved"] = "pair-approved"
    token: str
    host_id: str


class PairRejectedMessage(BaseModel):
    type: Literal["pair-rejected"] = "pair-rejected"
    reason: str


class AuthenticateFailedMessage(BaseModel):
    type: Literal["authenticate-failed"] = "authenticate-failed"


class ReleasePeerMessage(BaseModel):
    type: Literal["release-peer"] = "release-peer"


InboundMessage = Union[
    CreateSessionMessage,
    JoinSessionMessage,
    SdpMessage,
    IceCandidateMessage,
    RegisterHostMessage,
    AuthenticateMessage,
    PairApprovedMessage,
    PairRejectedMessage,
    AuthenticateFailedMessage,
    ReleasePeerMessage,
]

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
    "register-host": RegisterHostMessage,
    "authenticate": AuthenticateMessage,
    "pair-approved": PairApprovedMessage,
    "pair-rejected": PairRejectedMessage,
    "authenticate-failed": AuthenticateFailedMessage,
    "release-peer": ReleasePeerMessage,
}


def parse_inbound_message(raw: dict) -> InboundMessage:
    model = _INBOUND_MODELS.get(raw.get("type"))
    if model is None:
        raise ValueError(f"Unknown message type: {raw.get('type')!r}")
    return model.model_validate(raw)
