from app.modules.rag.schemas import RagSearchMatch


class ScoreReranker:
    def rerank(self, matches: list[RagSearchMatch]) -> list[RagSearchMatch]:
        return sorted(matches, key=lambda match: match.score, reverse=True)
