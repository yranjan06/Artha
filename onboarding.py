from memory import Memory


def needs_onboarding(memory: Memory) -> bool:
    return not bool(memory.user_profile.get("name"))
