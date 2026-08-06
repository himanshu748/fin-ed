from fined.provider_safety import ProviderErrorSanitizingLLM


def test_prewarm_forwards_current_livekit_keyword_arguments() -> None:
    calls: list[dict[str, object]] = []

    class Provider:
        def prewarm(self, **kwargs: object) -> None:
            calls.append(kwargs)

    wrapper = object.__new__(ProviderErrorSanitizingLLM)
    wrapper._provider_llm = Provider()  # type: ignore[assignment]
    loop = object()

    wrapper.prewarm(loop=loop)  # type: ignore[arg-type]

    assert calls == [{"loop": loop}]
