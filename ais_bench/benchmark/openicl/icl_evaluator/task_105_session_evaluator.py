from ais_bench.benchmark.openicl.icl_evaluator.json_field_evaluator import JsonFieldEvaluator


class Task105SessionEvaluator(JsonFieldEvaluator):
    """Strictly score turns and aggregate the primary metric by conversation."""

    def score(self, predictions, references, test_set=None):
        result = super().score(predictions, references)
        turn_accuracy = result.get("accuracy", 0.0)
        if test_set is None or len(test_set) != len(predictions):
            result["turn_accuracy"] = turn_accuracy
            return result

        session_scores = {}
        for detail, item in zip(result["details"], test_set):
            session_id = item.get("session_id")
            if session_id is None:
                result["turn_accuracy"] = turn_accuracy
                return result
            session_scores.setdefault(str(session_id), []).append(detail["eval_res"] is True)

        session_accuracy = (
            sum(all(scores) for scores in session_scores.values())
            / len(session_scores)
            * 100
            if session_scores else 0.0
        )
        session_avg_turn_accuracy = (
            sum(sum(scores) / len(scores) for scores in session_scores.values())
            / len(session_scores)
            * 100
            if session_scores else 0.0
        )
        result["turn_accuracy"] = turn_accuracy
        result["session_accuracy"] = session_accuracy
        result["session_avg_turn_accuracy"] = session_avg_turn_accuracy
        result["accuracy"] = session_accuracy
        return result
