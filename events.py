from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class OverridingSettings:
    humanSLProfile: Optional[str] = None

    @staticmethod
    def fromDict(data: Optional[dict]) -> Optional["OverridingSettings"]:
        if data == None:
            return None
        if len(data) == 0:
            return None

        human_sl_profile = None
        if "humanSLProfile" in data:
            human_sl_profile = data["humanSLProfile"]

        return OverridingSettings(human_sl_profile)


@dataclass(frozen=True)
class KatagoQuery:
    id: str
    moves: List[List[str]]
    rules: str
    komi: float
    boardXSize: int
    boardYSize: int
    analyzeTurns: Optional[List[int]] = None
    initialStone: Optional[List[List[str]]] = None
    initialPlayer: Optional[str] = None
    includePolicy: bool = False
    maxVisits: Optional[int] = None
    overridingSettings: Optional[OverridingSettings] = None

    @staticmethod
    def fromDict(data: dict) -> "KatagoQuery":
        builder = KatagoQuery.builder()

        builder.id(data["id"])

        if "moves" in data and data["moves"] != None:
            builder.moves(data["moves"])
        else:
            builder.moves([])

        builder.rules(data["rules"])
        builder.komi(data["komi"])
        builder.boardXSize(data["boardXSize"])
        builder.boardYSize(data["boardYSize"])

        if "analyzeTurns" in data:
            builder.analyzeTurns(data["analyzeTurns"])

        if "initialStone" in data:
            builder.initialStone(data["initialStone"])

        if "initialPlayer" in data:
            builder.initialPlayer(data["initialPlayer"])

        if "includePolicy" in data:
            builder.includePolicy(data["includePolicy"])

        if "maxVisits" in data:
            builder.maxVisits(data["maxVisits"])

        if "overridingSettings" in data:
            builder.overridingSettings(OverridingSettings.fromDict(data["overridingSettings"]))

        return builder.build()

    def toQueryDict(self) -> dict:
        payload = {}

        payload["id"] = self.id
        payload["moves"] = self.moves
        payload["rules"] = self.rules
        payload["komi"] = self.komi
        payload["boardXSize"] = self.boardXSize
        payload["boardYSize"] = self.boardYSize
        payload["includePolicy"] = self.includePolicy

        if self.analyzeTurns != None:
            payload["analyzeTurns"] = self.analyzeTurns

        if self.initialStone != None:
            # O protocolo de análise do KataGo espera a chave "initialStones"
            # (no plural), diferente do nome do campo recebido no evento.
            payload["initialStones"] = self.initialStone

        if self.initialPlayer != None:
            payload["initialPlayer"] = self.initialPlayer

        if self.maxVisits != None:
            payload["maxVisits"] = self.maxVisits

        if self.overridingSettings != None:
            # O protocolo de análise do KataGo espera a chave "overrideSettings"
            # (sem "ing"), diferente do nome do campo recebido no evento.
            payload["overrideSettings"] = {
                "humanSLProfile": self.overridingSettings.humanSLProfile,
            }

        return payload

    @staticmethod
    def builder() -> "KatagoQueryBuilder":
        return KatagoQueryBuilder()

    def toBuilder(self) -> "KatagoQueryBuilder":
        builder = KatagoQueryBuilder()

        builder.id(self.id)
        builder.moves(self.moves)
        builder.rules(self.rules)
        builder.komi(self.komi)
        builder.boardXSize(self.boardXSize)
        builder.boardYSize(self.boardYSize)
        builder.analyzeTurns(self.analyzeTurns)
        builder.initialStone(self.initialStone)
        builder.initialPlayer(self.initialPlayer)
        builder.includePolicy(self.includePolicy)
        builder.maxVisits(self.maxVisits)
        builder.overridingSettings(self.overridingSettings)

        return builder


class KatagoQueryBuilder:
    """Equivalente ao builder gerado pelo Lombok @Builder na classe Java KatagoQuery."""

    def __init__(self):
        self._id = None
        self._moves = None
        self._rules = None
        self._komi = None
        self._board_x_size = None
        self._board_y_size = None
        self._analyze_turns = None
        self._initial_stone = None
        self._initial_player = None
        self._include_policy = False
        self._max_visits = None
        self._overriding_settings = None

    def id(self, value) -> "KatagoQueryBuilder":
        self._id = value
        return self

    def moves(self, value) -> "KatagoQueryBuilder":
        self._moves = value
        return self

    def rules(self, value) -> "KatagoQueryBuilder":
        self._rules = value
        return self

    def komi(self, value) -> "KatagoQueryBuilder":
        self._komi = value
        return self

    def boardXSize(self, value) -> "KatagoQueryBuilder":
        self._board_x_size = value
        return self

    def boardYSize(self, value) -> "KatagoQueryBuilder":
        self._board_y_size = value
        return self

    def analyzeTurns(self, value) -> "KatagoQueryBuilder":
        self._analyze_turns = value
        return self

    def initialStone(self, value) -> "KatagoQueryBuilder":
        self._initial_stone = value
        return self

    def initialPlayer(self, value) -> "KatagoQueryBuilder":
        self._initial_player = value
        return self

    def includePolicy(self, value) -> "KatagoQueryBuilder":
        self._include_policy = value
        return self

    def maxVisits(self, value) -> "KatagoQueryBuilder":
        self._max_visits = value
        return self

    def overridingSettings(self, value) -> "KatagoQueryBuilder":
        self._overriding_settings = value
        return self

    def build(self) -> KatagoQuery:
        return KatagoQuery(
            id=self._id,
            moves=self._moves,
            rules=self._rules,
            komi=self._komi,
            boardXSize=self._board_x_size,
            boardYSize=self._board_y_size,
            analyzeTurns=self._analyze_turns,
            initialStone=self._initial_stone,
            initialPlayer=self._initial_player,
            includePolicy=self._include_policy,
            maxVisits=self._max_visits,
            overridingSettings=self._overriding_settings,
        )


@dataclass(frozen=True)
class AnalysisDTO:
    sgf: Optional[str] = None
    correlationId: str = None
    chatId: Optional[int] = None

    @staticmethod
    def fromDict(data: dict) -> "AnalysisDTO":
        sgf = None
        if "sgf" in data:
            sgf = data["sgf"]

        correlation_id = data["correlationId"]

        chat_id = None
        if "chatId" in data:
            chat_id = data["chatId"]

        return AnalysisDTO(sgf, correlation_id, chat_id)


@dataclass(frozen=True)
class AnalysisCreatedEvent:
    analysisDTO: AnalysisDTO
    katagoQuery: KatagoQuery

    @staticmethod
    def fromDict(data: dict) -> "AnalysisCreatedEvent":
        analysis_dto = AnalysisDTO.fromDict(data["analysisDTO"])
        katago_query = KatagoQuery.fromDict(data["katagoQuery"])

        return AnalysisCreatedEvent(analysis_dto, katago_query)
